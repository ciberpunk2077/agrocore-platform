"""D7C local GUI only. Never launch from tests with persistent credentials."""
from contextlib import contextmanager

ERROR = 'No se pudo validar o abrir el visor DEMO. No se revelaron credenciales.'


@contextmanager
def validated_accounts():
    from django.conf import settings
    from . import backup, rehearsal_command as runtime
    from .demo_view import RUN_ID, verified_locations
    from .windows_acl import verify_private
    from .preflight import safe_file
    if settings.SETTINGS_MODULE != 'config.settings.demo_view':
        raise ValueError(ERROR)
    plan = verified_locations()
    if plan.run_id != RUN_ID or plan.testing:
        raise ValueError(ERROR)
    authority = None
    bundle = None
    accounts = []
    try:
        with backup.frozen_source(plan.original), backup.frozen_source(plan.copy):
            verified_locations()
            backup.check_migrations(plan.copy)
            authority = runtime._Authority(plan)
            grants = list(plan.grants.glob('*.json'))
            if len(grants) != 1 or len(list(plan.grants.iterdir())) != 1 or len(list(plan.ledger.iterdir())) != 1:
                raise ValueError(ERROR)
            # Validates signed run/SID binding and durable consumption, never consumes again.
            binding = runtime._binding(plan, authority, grants[0])
            files = [grants[0], plan.receipt_file, *plan.ledger.iterdir()]
            files += [plan.keys / (name + '.key') for name in authority.keys]
            for directory in plan.deliveries:
                runtime._private_tree(directory, plan.artifact_root)
                if {p.name for p in directory.iterdir()} != {'d2.bundle'}:
                    raise ValueError(ERROR)
                files.append(directory / 'd2.bundle')
            for path in files:
                verify_private(safe_file(path))
            before = {path: backup.digest(path) for path in files}
            if runtime._phase_status(plan, binding, authority) != dict.fromkeys(('D2', 'D3', 'D4'), 'complete'):
                raise ValueError(ERROR)
            bundle, state = runtime._read_bundle(plan, authority, plan.deliveries[0])
            if state != 'complete':
                raise ValueError(ERROR)
            # Bind the displayed bundle to the exact ciphertext verified above.
            if any(backup.digest(path) != digest for path, digest in before.items()):
                raise ValueError(ERROR)
            authority.verify_files()
            orgs = {}
            from apps.organizations.models import Organization
            with runtime._readonly_connection(plan.copy):
                ids = bundle['receipt']['payload']['inventory']['organizations']['ids']
                orgs = {str(org.pk): org.name for org in Organization._base_manager.filter(pk__in=ids)}
            accounts = [dict(entry, organization=orgs[entry['organization_uuid']]) for entry in bundle['credentials']]
            if len(accounts) != 30 or len({a['user_uuid'] for a in accounts}) != 30 or len(orgs) != 5:
                raise ValueError(ERROR)
            yield accounts
    finally:
        for account in accounts:
            account.clear()
        accounts.clear()
        if bundle is not None:
            bundle.clear()
        if authority is not None:
            authority.keys.clear()


class Selection:
    """Only receives fully validated accounts; no history or bulk export."""
    def __init__(self, accounts, confirm, clipboard, schedule):
        self.accounts, self.confirm = accounts, confirm
        self.clipboard, self.schedule = clipboard, schedule
        self.selected = None
        self.copied = None
        self.visible = False
        self.closed = False
        self.generation = 0

    def select(self, index):
        if self.closed or not 0 <= index < len(self.accounts):
            raise ValueError(ERROR)
        self.visible = False
        self.selected = index

    def reveal(self):
        if self.closed or self.selected is None:
            return False
        if self.visible:
            self.visible = False
        elif self.confirm('Mostrar temporalmente la contraseña seleccionada?'):
            self.visible = True
        return self.visible

    def copy(self):
        if self.closed or self.selected is None or not self.confirm('Copiar la contraseña seleccionada durante 30 segundos?'):
            return False
        self.clear_clipboard()
        value = self.accounts[self.selected]['password']
        self.clipboard.set(value)
        self.copied = value
        self.generation += 1
        generation = self.generation
        self.schedule(30000, lambda: self.clear_clipboard() if generation == self.generation else None)
        return True

    def clear_clipboard(self):
        if self.copied is not None:
            try:
                if self.clipboard.get() == self.copied:
                    self.clipboard.clear()
            finally:
                self.copied = None

    def close(self):
        self.closed = True
        self.visible = False
        self.selected = None
        try:
            self.clear_clipboard()
        finally:
            self.accounts.clear()
            self.confirm = None


def show_window(root, accounts):
    import tkinter as tk
    from tkinter import ttk, messagebox

    class Clipboard:
        def get(self):
            try:
                return root.clipboard_get()
            except tk.TclError:
                return None
        def set(self, value):
            root.clipboard_clear()
            root.clipboard_append(value)
        def clear(self):
            root.clipboard_clear()

    root.title('AgroCore - Credenciales DEMO locales')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=18)
    frame.pack()
    ttk.Label(frame, text='Solo dataset DEMO autorizado. Una cuenta a la vez.').pack()
    organization = ttk.Combobox(frame, state='readonly', width=55, values=sorted({a['organization'] for a in accounts}))
    organization.pack(pady=8)
    user = ttk.Combobox(frame, state='readonly', width=55)
    user.pack(pady=8)
    email = tk.StringVar()
    secret = tk.StringVar()
    ttk.Entry(frame, textvariable=email, state='readonly', width=58).pack(pady=8)
    password = ttk.Entry(frame, textvariable=secret, state='readonly', show='*', width=58)
    password.pack(pady=8)
    # Prevent the entry's default copy/selection behavior bypassing confirmation.
    for event in ('<Control-c>', '<Control-C>', '<Control-Insert>', '<<Copy>>', '<<Cut>>', '<Button-3>'):
        password.bind(event, lambda event: 'break')
    state = Selection(accounts, lambda prompt: messagebox.askyesno('Confirmación local', prompt, parent=root), Clipboard(), root.after)
    indices = []
    def hide():
        state.visible = False
        secret.set('')
        password.configure(show='*')
    def choose_org(event=None):
        hide()
        state.selected = None
        email.set('')
        indices[:] = [i for i, a in enumerate(accounts) if a['organization'] == organization.get()]
        user.configure(values=[accounts[i]['role'] + ' | ' + accounts[i]['email'] for i in indices])
        user.set('')
    def choose_user(event=None):
        hide()
        state.select(indices[user.current()])
        email.set(accounts[state.selected]['email'])
    def reveal():
        if state.reveal():
            secret.set(accounts[state.selected]['password'])
            password.configure(show='')
            root.after(30000, hide)
        else:
            hide()
    def close():
        try:
            hide()
            email.set('')
            state.close()
        finally:
            root.destroy()
    organization.bind('<<ComboboxSelected>>', choose_org)
    user.bind('<<ComboboxSelected>>', choose_user)
    ttk.Button(frame, text='Mostrar / Ocultar contraseña', command=reveal).pack(pady=4)
    ttk.Button(frame, text='Copiar contraseña (30 s)', command=state.copy).pack(pady=4)
    ttk.Label(frame, text='El portapapeles puede ser leído por otros procesos locales.').pack(pady=8)
    ttk.Button(frame, text='Cerrar', command=close).pack()
    root.protocol('WM_DELETE_WINDOW', close)
    root.bind('<FocusOut>', lambda event: hide() if event.widget is root else None)
    root.deiconify()
    try:
        root.mainloop()
    finally:
        try:
            if not state.closed:
                hide()
                email.set('')
                state.close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


def main():
    import os
    import tkinter as tk
    from tkinter import messagebox
    root = None
    try:
        if os.name != 'nt':
            raise ValueError(ERROR)
        root = tk.Tk()
        root.withdraw()
        def callback_error(*ignored):
            try:
                messagebox.showerror('AgroCore DEMO', 'Operación interrumpida. Cierre el visor si el error persiste.', parent=root)
            except Exception:
                pass
        root.report_callback_exception = callback_error
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.demo_view'
        import logging
        logging.disable(logging.CRITICAL)
        import django
        django.setup()
        with validated_accounts() as accounts:
            show_window(root, accounts)
        return 0
    except Exception:
        if root is not None:
            try:
                messagebox.showerror('AgroCore DEMO', ERROR, parent=root)
                root.destroy()
            except Exception:
                pass
        return 1
