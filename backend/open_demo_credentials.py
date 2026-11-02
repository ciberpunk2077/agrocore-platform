"""No-console entry point. No secrets in arguments or error output."""
import sys
sys.dont_write_bytecode = True
sys.excepthook = lambda *ignored: None
if __name__ == '__main__':
    try:
        from apps.organizations.demo.credential_viewer import main
        sys.exit(main())
    except Exception:
        sys.exit(1)
