class PasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from core import views

        response = views.enforce_password_change(request)
        if response is not None:
            return response
        return self.get_response(request)
