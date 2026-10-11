# OryaSecurity Proxy Support for ZAI Provider

This document explains how to configure OryaSecurity as an HTTPS proxy for the ZAI (z.ai) LLM provider in OriaAI.

## Overview

The OryaSecurity proxy allows you to route all ZAI API requests through a security proxy for monitoring, filtering, and compliance purposes. This is implemented using standard HTTPS proxy configuration.

## Configuration

### Environment Variables

Add the following variables to your `.env` file:

```bash
# OryaSecurity proxy settings (optional)
ORYA_PROXY_URL=http://proxy.oryasecurity.internal:8443
ORYA_PROXY_KEY=your_orya_security_api_key_here
```

### Parameters

- `ORYA_PROXY_URL`: The URL of the OryaSecurity proxy (e.g., `http://proxy.oryasecurity.internal:8443`)
- `ORYA_PROXY_KEY`: The API key for authenticating to the OryaSecurity proxy

### Authentication

The OryaSecurity proxy key is used for Basic authentication to the proxy. The key is automatically added to the proxy URL as follows:

```
http://KEY@proxy.host:port
```

## Usage Example

### 1. Basic Configuration

```bash
# In your .env file
LLM_PROVIDER=ZAI
ZAI_API_KEY=your_zai_api_key
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
ZAI_MODEL=glm-4.5

# OryaSecurity proxy
ORYA_PROXY_URL=http://proxy.oryasecurity.internal:8443
ORYA_PROXY_KEY=your_orya_security_key
```

### 2. Without Proxy (Default Behavior)

If `ORYA_PROXY_URL` is not set, the ZAI provider will connect directly to `https://api.z.ai/api/paas/v4`:

```bash
# In your .env file
LLM_PROVIDER=ZAI
ZAI_API_KEY=your_zai_api_key
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
# ORYA_PROXY_URL and ORYA_PROXY_KEY are not set
```

## Technical Details

### Implementation

The proxy support is implemented by:

1. **Settings Configuration**: New fields `orya_proxy_url` and `orya_proxy_key` in the `Settings` class
2. **Validation**: Ensures that if `ORYA_PROXY_URL` is set, `ORYA_PROXY_KEY` must also be provided
3. **Proxy Configuration**: The proxy URL is passed to the underlying HTTP client via standard proxy configuration
4. **Authentication**: Basic authentication is configured using the proxy key

### HTTP Client

The implementation uses the standard HTTP client proxy configuration. The proxy settings are applied to both:
- LLM requests (via `ChatOpenAI`)
- Embedding requests (via `OpenAIEmbeddings`)

### Security

- The proxy key is stored as a plain text environment variable
- The proxy configuration is validated at application startup
- The proxy URL must use `http://` or `https://` protocol

## Testing

The proxy functionality is tested with the following test cases:

- `test_zai_with_orya_proxy`: Tests that the ZAI provider works with proxy configuration
- `test_zai_without_proxy`: Tests that the ZAI provider works without proxy (default behavior)
- `test_orya_proxy_url_validation`: Tests validation of proxy URL format
- `test_orya_proxy_key_validation`: Tests validation requiring proxy key when URL is set

Run the tests with:

```bash
python -m pytest tests/unit/test_orya_proxy.py -v
```

## Troubleshooting

### Common Issues

1. **Proxy Connection Errors**: Check that the proxy URL is accessible and the proxy is running
2. **Authentication Errors**: Verify that the `ORYA_PROXY_KEY` is correct
3. **SSL/TLS Errors**: Ensure the proxy certificate is trusted or configure SSL verification settings

### Debugging

To debug proxy issues, you can:

1. Check the application logs for connection errors
2. Test the proxy URL manually using curl or similar tools
3. Verify network connectivity to the proxy endpoint

## Notes

- The proxy configuration only applies to the ZAI provider
- If both `ORYA_PROXY_URL` and `ORYA_PROXY_KEY` are set, the proxy will be used
- If `ORYA_PROXY_URL` is set but `ORYA_PROXY_KEY` is missing, the application will fail to start with a validation error
- The proxy settings do not affect other providers (OpenAI, Anthropic, etc.)