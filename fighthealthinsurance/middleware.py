from typing import Callable, Dict, List
import re
import time
from django.http import HttpRequest, HttpResponseBase, HttpResponseForbidden
from django.conf import settings
from django.core.cache import cache 

class SecurityScanMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]):
        self.get_response = get_response
        self.security_patterns = [
            r'(?i)(<|%3C)script',  # XSS attempts
            r'(?i)(union\s+select|insert\s+into|drop\s+table|delete\s+from)',  # SQL injection attempts
            r'(?i)(/\.\./|\.\./)',  # Path traversal attempts
            r'(?i)(exec\s+|eval\s*\()',  # Code injection attempts
            r'(?i)(file|system|phpinfo)\s*\(',  # PHP injection attempts
        ]
        self.patterns = [re.compile(pattern) for pattern in self.security_patterns]
        self.rate_limit = 3000  # requests
        self.time_window = 300  # 5 minutes in seconds

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        # Skip security checks for test environment
        if settings.TESTING:
            return self.get_response(request)

        # Check for security scan patterns
        path = request.path
        query = request.META.get('QUERY_STRING', '')
        content = path + query
        
        # Get client IP with a default value and type checking
        client_ip: str = request.META.get('REMOTE_ADDR', '')
        if not client_ip:
            return HttpResponseForbidden("Could not determine client IP")

        # Skip rate limiting for authenticated staff/admin users
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return self.get_response(request)

        # Rate limiting for sensitive endpoints
        sensitive_patterns = ['login', 'logout', 'password_reset', 'rest_verify_email', 'admin', 'webhook']
        if any(pattern in path.lower() for pattern in sensitive_patterns):
            # Use cache-based rate limiting instead of in-memory dictionary
            cache_key = f"ratelimit:{client_ip}:{path.split('/')[1]}"
            
            # Get current count from cache
            request_count = cache.get(cache_key, 0)
            
            # Check if rate limit exceeded
            if request_count >= self.rate_limit:
                return HttpResponseForbidden("Rate limit exceeded")
            
            # Increment the counter and set expiration
            cache.set(cache_key, request_count + 1, self.time_window)

        # Also check request body for security patterns if it exists
        if request.method in ['POST', 'PUT', 'PATCH']:
            # Check content type to determine how to handle the body
            content_type = request.META.get('CONTENT_TYPE', '').lower()
            
            # Skip binary file uploads and other non-text content types
            if content_type and any(ct in content_type for ct in ['image/', 'video/', 'audio/', 'application/octet-stream', 'application/pdf']):
                # Binary file upload - skip pattern matching but could implement file type validation here
                pass
            else:
                # For text-based content, try to decode and check
                try:
                    body = request.body.decode('utf-8')
                    for pattern in self.patterns:
                        if pattern.search(body):
                            return HttpResponseForbidden("Security violation detected")
                except UnicodeDecodeError:
                    # If we expected text but got binary data, this could be suspicious
                    if content_type and any(ct in content_type for ct in ['text/', 'application/json', 'application/xml', 'application/javascript']):
                        return HttpResponseForbidden("Invalid encoding for declared content type")
                    # Otherwise, it might be an undeclared binary upload - could log this for monitoring

        response: HttpResponseBase = self.get_response(request)
        return response