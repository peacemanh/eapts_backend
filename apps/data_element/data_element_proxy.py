import logging
import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

logger = logging.getLogger(__name__)


class DHIS2ProxyView(APIView):
    """
    Simple proxy that forwards any request to DHIS2 and returns the exact response
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, path):
        """Forward GET request to DHIS2"""
        return self._forward_request('GET', request, path)
    
    def post(self, request, path):
        """Forward POST request to DHIS2"""
        return self._forward_request('POST', request, path)
    
    def put(self, request, path):
        """Forward PUT request to DHIS2"""
        return self._forward_request('PUT', request, path)
    
    def delete(self, request, path):
        """Forward DELETE request to DHIS2"""
        return self._forward_request('DELETE', request, path)
    
    def _forward_request(self, method, request, path):
        try:
            # DHIS2 configuration from settings
            dhis2_url = settings.DHIS2_BASE_URL.rstrip('/')
            auth = (settings.DHIS2_USERNAME, settings.DHIS2_PASSWORD)
            
            # Build full URL
            url = f"{dhis2_url}/{path.lstrip('/')}"
            
            # Forward all query parameters exactly as received
            params = request.GET.dict()
            
            logger.info(f"Proxying {method} to DHIS2: {url}")
            
            # Make request to DHIS2
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=request.data if method in ['POST', 'PUT', 'PATCH'] else None,
                auth=auth,
                timeout=30,
                headers={'Accept': 'application/json'}
            )
            
            # Return exactly what DHIS2 returned
            try:
                data = response.json()
                return JsonResponse(data, status=response.status_code, safe=False)
            except:
                return HttpResponse(
                    response.text, 
                    status=response.status_code,
                    content_type=response.headers.get('Content-Type', 'text/plain')
                )
            
        except requests.exceptions.Timeout:
            return JsonResponse({'error': 'DHIS2 timeout'}, status=504)
        except requests.exceptions.ConnectionError:
            return JsonResponse({'error': 'Cannot connect to DHIS2'}, status=502)
        except Exception as e:
            logger.error(f"Proxy error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)


class DHIS2TestConnectionView(APIView):
    """Test DHIS2 connection"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            dhis2_url = settings.DHIS2_BASE_URL.rstrip('/')
            auth = (settings.DHIS2_USERNAME, settings.DHIS2_PASSWORD)
            
            response = requests.get(
                f"{dhis2_url}/me", 
                auth=auth, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return JsonResponse({
                    'success': True,
                    'user': data.get('name'),
                    'username': data.get('userCredentials', {}).get('username'),
                    'version': data.get('systemInfo', {}).get('version')
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'DHIS2 returned {response.status_code}'
                }, status=response.status_code)
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)