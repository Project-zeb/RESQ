from django.http import JsonResponse

from disaster_api.django_state import get_state


class ApiKeyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        state = get_state()
        settings = state["settings"]
        auth_service = state["auth_service"]

        if not request.path.startswith("/api/"):
            return self.get_response(request)

        requires_admin = request.path.startswith("/api/admin/")
        if not settings.require_api_key and not requires_admin:
            return self.get_response(request)

        principal = auth_service.authenticate_request(request, require_admin=requires_admin)
        if principal is not None:
            request.auth_principal = principal
            return self.get_response(request)

        return JsonResponse(
            {
                "error": "Unauthorized",
                "message": (
                    f"Provide API key in {settings.api_key_header} "
                    f"or {settings.admin_api_key_header}, "
                    "or use Authorization Bearer JWT."
                ),
            },
            status=401,
        )
