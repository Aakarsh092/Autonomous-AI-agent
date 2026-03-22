"""
Unit tests for the EndpointParser.
Run with: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.parser import EndpointParser, APIEndpoint


@pytest.fixture
def parser():
    return EndpointParser()


class TestExpressRouteExtraction:

    def test_basic_get_route(self, parser):
        content = "app.get('/api/Products', getProducts())"
        eps = parser.parse_file("server.ts", content)
        assert len(eps) == 1
        assert eps[0].method == "GET"
        assert eps[0].path == "/api/Products"

    def test_post_route(self, parser):
        content = "app.post('/rest/user/login', login())"
        eps = parser.parse_file("server.ts", content)
        assert eps[0].method == "POST"
        assert eps[0].path == "/rest/user/login"

    def test_put_delete_routes(self, parser):
        content = """
app.put('/api/Users/:id', updateUser())
app.delete('/api/Users/:id', deleteUser())
"""
        eps = parser.parse_file("server.ts", content)
        methods = {e.method for e in eps}
        assert "PUT" in methods
        assert "DELETE" in methods

    def test_path_params_extracted(self, parser):
        content = "app.get('/rest/track-order/:id', trackOrder())"
        eps = parser.parse_file("server.ts", content)
        assert "id" in eps[0].path_params

    def test_multiple_path_params(self, parser):
        content = "app.get('/api/Users/:userId/orders/:orderId', getOrder())"
        eps = parser.parse_file("server.ts", content)
        assert "userId" in eps[0].path_params
        assert "orderId" in eps[0].path_params

    def test_auth_required_detected(self, parser):
        content = "app.get('/rest/wallet/balance', security.isAuthorized(), getBalance())"
        eps = parser.parse_file("server.ts", content)
        assert eps[0].auth_required is True
        assert "isAuthorized" in eps[0].middlewares

    def test_deny_all_detected(self, parser):
        content = "app.delete('/api/Products/:id', security.denyAll())"
        eps = parser.parse_file("server.ts", content)
        assert eps[0].auth_required is True
        assert "denyAll" in eps[0].middlewares

    def test_no_auth_on_public_route(self, parser):
        content = "app.get('/api/Products', getProducts())"
        eps = parser.parse_file("server.ts", content)
        assert eps[0].auth_required is False

    def test_tags_inferred(self, parser):
        content = "app.get('/api/Products', getProducts())"
        eps = parser.parse_file("server.ts", content)
        assert "Products" in eps[0].tags

    def test_multiple_routes_parsed(self, parser):
        content = """
app.get('/api/Products', getProducts())
app.post('/api/Products', createProduct())
app.get('/api/Products/:id', getProductById())
app.put('/api/Products/:id', updateProduct())
app.delete('/api/Products/:id', deleteProduct())
"""
        eps = parser.parse_file("server.ts", content)
        assert len(eps) == 5

    def test_deduplication(self, parser):
        content = """
app.get('/api/Products', getProducts())
app.get('/api/Products', getProductsAgain())
"""
        eps = parser.parse_file("server.ts", content)
        assert len(eps) == 1

    def test_router_prefix(self, parser):
        content = "router.post('/login', handleLogin())"
        eps = parser.parse_file("routes/login.ts", content)
        assert eps[0].method == "POST"

    def test_skip_non_path_string(self, parser):
        content = "app.get('not-a-path', handler())"
        eps = parser.parse_file("server.ts", content)
        assert len(eps) == 0


class TestSchemaGeneration:

    def test_login_request_schema(self, parser):
        content = "app.post('/rest/user/login', login())"
        ep = parser.parse_file("server.ts", content)[0]
        props = ep.request_schema.get("properties", {})
        assert "email" in props
        assert "password" in props

    def test_get_has_no_body_schema(self, parser):
        content = "app.get('/api/Products', getProducts())"
        ep = parser.parse_file("server.ts", content)[0]
        assert "properties" not in ep.request_schema or ep.request_schema.get("properties") == {}

    def test_product_response_schema(self, parser):
        content = "app.get('/api/Products', getProducts())"
        ep = parser.parse_file("server.ts", content)[0]
        success = ep.response_schema.get("success", {})
        assert success.get("status") == 200
        props = success["schema"]["properties"]
        assert "price" in props

    def test_feedback_request_schema(self, parser):
        content = "app.post('/api/Feedbacks', submitFeedback())"
        ep = parser.parse_file("server.ts", content)[0]
        props = ep.request_schema.get("properties", {})
        assert "comment" in props
        assert "rating" in props

    def test_user_response_schema(self, parser):
        content = "app.get('/api/Users/:id', security.isAuthorized(), getUser())"
        ep = parser.parse_file("server.ts", content)[0]
        success = ep.response_schema.get("success", {})
        props = success["schema"]["properties"]
        assert "email" in props
        assert "role" in props

    def test_basket_request_schema(self, parser):
        content = "app.post('/api/BasketItems', security.isAuthorized(), addItem())"
        ep = parser.parse_file("server.ts", content)[0]
        props = ep.request_schema.get("properties", {})
        assert "ProductId" in props
        assert "quantity" in props

    def test_delete_response_status(self, parser):
        content = "app.delete('/api/Users/:id', security.isAuthorized(), deleteUser())"
        ep = parser.parse_file("server.ts", content)[0]
        assert ep.response_schema["success"]["status"] == 200
        assert ep.response_schema["error"]["status"] == 404

    def test_post_response_status(self, parser):
        content = "app.post('/api/Users', createUser())"
        ep = parser.parse_file("server.ts", content)[0]
        assert ep.response_schema["success"]["status"] == 201


class TestFrisbyTestParser:

    def test_frisby_get_extracted(self, parser):
        content = "frisby.get(URL + '/api/Products').expect('status', 200)"
        eps = parser.parse_file("test/productSpec.ts", content)
        assert any(e.method == "GET" and "/api/Products" in e.path for e in eps)

    def test_frisby_post_extracted(self, parser):
        content = "frisby.post(URL + '/rest/user/login', { email: 'a@b.com' })"
        eps = parser.parse_file("test/loginSpec.ts", content)
        assert any(e.method == "POST" for e in eps)


class TestOpenAPIYAMLParser:

    def test_openapi_yaml_paths(self, parser):
        content = """\
/api/Products:
  get:
    summary: Get all products
  post:
    summary: Create a product
/api/Users:
  get:
    summary: Get all users
"""
        eps = parser.parse_file("swagger.yaml", content)
        methods = {e.method for e in eps}
        assert "GET" in methods
        assert "POST" in methods
        assert len(eps) == 3


class TestPathNormalization:

    def test_leading_slash_added(self, parser):
        content = "app.get('api/Products', getProducts())"
        eps = parser.parse_file("server.ts", content)
        if eps:
            assert eps[0].path.startswith("/")

    def test_source_file_recorded(self, parser):
        content = "app.get('/api/Products', getProducts())"
        eps = parser.parse_file("routes/products.ts", content)
        assert eps[0].source_file == "routes/products.ts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
