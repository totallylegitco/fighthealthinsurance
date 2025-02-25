import pytest
import aiohttp
from unittest.mock import Mock, patch
import asyncio

class TestBadUrls:
    @pytest.mark.asyncio
    async def test_handle_bad_url(self):
        """Test handling of invalid URLs in async context"""
        async with aiohttp.ClientSession() as session:
            bad_url = "http://invalid.domain.that.does.not.exist"
            
            with pytest.raises(aiohttp.ClientError):
                async with session.get(bad_url) as response:
                    await response.text()

    @pytest.mark.asyncio
    async def test_handle_timeout(self):
        """Test handling of timeout scenarios"""
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=0.001)
            with pytest.raises(asyncio.TimeoutError):
                async with session.get('http://example.com', timeout=timeout) as response:
                    await response.text()

    @pytest.mark.asyncio
    async def test_malformed_url(self):
        """Test handling of malformed URLs"""
        async with aiohttp.ClientSession() as session:
            malformed_url = "not-a-valid-url"
            
            with pytest.raises(aiohttp.InvalidURL):
                async with session.get(malformed_url) as response:
                    await response.text()

    @pytest.mark.asyncio
    async def test_invalid_ports(self):
        """Test URLs with invalid ports"""
        async with aiohttp.ClientSession() as session:
            bad_port_url = "http://localhost:99999"
            
            with pytest.raises(aiohttp.ClientError):
                async with session.get(bad_port_url) as response:
                    await response.text()

