"""
JWT Authentication Middleware for WebSocket connections.

WebSocket connections cannot use HTTP headers for authentication because
the JavaScript WebSocket API does not support custom headers. Instead,
we extract and validate JWT tokens from query parameters.

Architecture:
- Extracts token from query string: ws://domain/ws/alerts/?token=JWT_TOKEN
- Validates token using Django's SECRET_KEY
- Populates scope['user'] with authenticated user or AnonymousUser
- Integrates with Channels' scope for use in consumers

Security Considerations:
- Uses HTTPS/WSS in production only
- Tokens should have short expiration times
- Tokens are logged but never displayed
- AnonymousUser fallback prevents connection rejection
"""

from urllib.parse import parse_qs
import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


@database_sync_to_async
def get_user_from_db(user_id):
    """
    Fetch user from database asynchronously.
    
    Args:
        user_id: Primary key of user to fetch
    
    Returns:
        User instance or AnonymousUser if not found
    
    Note:
        This is wrapped with @database_sync_to_async to ensure
        database operations don't block the async event loop.
    """
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning(f"User not found for id: {user_id}")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"Error fetching user: {str(e)}", exc_info=True)
        return AnonymousUser()


class JWTAuthMiddleware:
    """
    ASGI middleware for JWT authentication via query parameters.
    
    Usage:
        Wrap URLRouter with this middleware in asgi.py:
        
        application = ProtocolTypeRouter({
            "http": django_asgi_app,
            "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
        })
    
    Client Usage (JavaScript):
        const token = localStorage.getItem('auth_token');
        const socket = new WebSocket(`ws://localhost:9000/ws/alerts/?token=${token}`);
    
    Token Format:
        JWT token with payload: { "user_id": int, "exp": timestamp }
    """
    
    def __init__(self, app):
        """
        Initialize middleware.
        
        Args:
            app: ASGI application to wrap (typically URLRouter)
        """
        self.app = app

    async def __call__(self, scope, receive, send):
        """
        ASGI interface implementation.
        
        Args:
            scope: Connection scope (contains connection metadata)
            receive: Callable to receive messages from client
            send: Callable to send messages to client
        
        Returns:
            Awaitable that processes the connection
        
        Flow:
            1. Extract query string from scope
            2. Parse token from query parameters
            3. Validate JWT token
            4. Fetch user from database
            5. Add user to scope
            6. Pass control to wrapped application
        """
        # Only process WebSocket connections
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return
        
        # Extract and parse query string
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]
        
        # Attempt to authenticate with token
        if token:
            try:
                # Security best practice: Always explicitly define algorithms to prevent
                # algorithm confusion attacks
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get("user_id")
                
                if user_id:
                    scope["user"] = await get_user_from_db(user_id)
                    logger.debug(f"WebSocket user authenticated: {user_id}")
                else:
                    scope["user"] = AnonymousUser()
                    logger.warning("Token missing user_id claim")
                    
            except jwt.ExpiredSignatureError:
                scope["user"] = AnonymousUser()
                logger.warning("Expired JWT token used for WebSocket connection")
            except jwt.DecodeError as e:
                scope["user"] = AnonymousUser()
                logger.warning(f"Invalid JWT token: {str(e)}")
            except KeyError:
                scope["user"] = AnonymousUser()
                logger.warning("Malformed JWT token payload")
            except Exception as e:
                scope["user"] = AnonymousUser()
                logger.error(f"Unexpected error in JWT auth: {str(e)}", exc_info=True)
        else:
            scope["user"] = AnonymousUser()
            logger.debug("WebSocket connection without authentication token")
        
        # Pass control to wrapped application with authenticated scope
        await self.app(scope, receive, send)


def generate_ws_token(user):
    """
    Generate a JWT token for WebSocket authentication.
    
    Args:
        user: Django User instance
    
    Returns:
        JWT token string
    
    Example:
        from core.auth_middleware import generate_ws_token
        token = generate_ws_token(request.user)
        # Send to frontend via API
    """
    from datetime import datetime, timedelta, timezone
    
    payload = {
        "user_id": user.id,
        "username": user.username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
    }
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token
