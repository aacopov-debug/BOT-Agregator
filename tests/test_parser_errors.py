import pytest
from unittest.mock import MagicMock, patch
from app.services.parsers.base import BaseParser, ParserBlockError, ParserError

class MockResponse:
    def __init__(self, status=200, json_data=None, text_data=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return self._json_data
    async def text(self): return self._text_data

class TestParser(BaseParser):
    async def parse(self, job_service) -> int:
        return 0

@pytest.mark.asyncio
async def test_base_parser_block_error():
    parser = TestParser()
    mock_resp = MockResponse(status=403)
    mock_request = MagicMock(return_value=mock_resp)
    
    with patch("aiohttp.ClientSession.request", mock_request):
        with pytest.raises(ParserBlockError):
            await parser._request_with_retry("GET", "http://test.com")

@pytest.mark.asyncio
async def test_base_parser_general_error():
    parser = TestParser()
    mock_resp = MockResponse(status=500)
    mock_request = MagicMock(return_value=mock_resp)
    
    with patch("aiohttp.ClientSession.request", mock_request):
        with pytest.raises(ParserError):
            await parser._request_with_retry("GET", "http://test.com")

@pytest.mark.asyncio
async def test_base_parser_success_json():
    parser = TestParser()
    expected_data = {"key": "value"}
    mock_resp = MockResponse(status=200, json_data=expected_data)
    mock_request = MagicMock(return_value=mock_resp)
    
    with patch("aiohttp.ClientSession.request", mock_request):
        data = await parser._request_with_retry("GET", "http://test.com")
        assert data == expected_data

@pytest.mark.asyncio
async def test_base_parser_get_html():
    parser = TestParser()
    expected_html = "<html><body>Test</body></html>"
    mock_resp = MockResponse(status=200, text_data=expected_html)
    mock_request = MagicMock(return_value=mock_resp)
    
    with patch("aiohttp.ClientSession.request", mock_request):
        html = await parser._get_html("http://test.com")
        assert html == expected_html

@pytest.mark.asyncio
async def test_base_parser_proxy_rotation():
    """Проверка, что при 403 ошибке парсер пробует другой прокси."""
    parser = TestParser()
    
    # Первый запрос возвращает 403, второй 200
    mock_resp1 = MockResponse(status=403)
    mock_resp2 = MockResponse(status=200, json_data={"success": True})
    
    mock_request = MagicMock()
    mock_request.side_effect = [mock_resp1, mock_resp2]
    
    from app.utils.proxy_manager import proxy_manager
    proxy_manager.use_proxies = True
    proxy_manager.proxies = ["http://proxy1", "http://proxy2"]
    
    with patch("aiohttp.ClientSession.request", mock_request):
        with patch.object(proxy_manager, 'mark_failed') as mock_mark:
            data = await parser._request_with_retry("GET", "http://test.com", retries=2)
            assert data == {"success": True}
            mock_mark.assert_called_once()
