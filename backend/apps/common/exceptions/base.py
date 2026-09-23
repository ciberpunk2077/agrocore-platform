class BusinessException(Exception):
    """
    Excepción base para errores de negocio.
    """

    default_message = "Ocurrió un error de negocio."

    def __init__(self, message=None):
        self.message = message or self.default_message
        super().__init__(self.message)