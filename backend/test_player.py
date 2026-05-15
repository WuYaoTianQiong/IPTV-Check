import base64, urllib.parse

# User's URL parameter (from the browser address bar)
user_param = 'aHR0cCUzQSUyRiUyRmhscy5ubnR2LmNuJTJGbm5saXZlJTJGU0xUVl9BLm0zdTg='

# Step 1: FastAPI automatically URL-decodes the query param
# Browser sent: /player?url=aHR0cCUz... (already URL-safe base64)
# FastAPI gives us: aHR0cCUzQSUyRiUyRmhscy5ubnR2LmNuJTJGbm5saXZlJTJGU0xUVl9BLm0zdTg=
fastapi_received = user_param
print("Step 1 - FastAPI received:", fastapi_received)

# Step 2: player_page does base64 decode
step2 = base64.b64decode(fastapi_received).decode("utf-8")
print("Step 2 - After base64 decode:", step2)
# Result: http%3A%2F%2Fhls.nntv.cn%2Fnnlive%2FSLTV_A.m3u8

# Step 3: player_page does URL unquote
stream_url = urllib.parse.unquote(step2)
print("Step 3 - After unquote:", stream_url)
# Result: http://hls.nntv.cn/nnlive/SLTV_A.m3u8

# Step 4: render_player_html encodes for proxy
proxy_b64 = base64.b64encode(stream_url.encode()).decode()
print("Step 4 - Proxy base64:", proxy_b64)

# Step 5: render_player_html URL-quotes for HTML safety
proxy_safe = urllib.parse.quote(proxy_b64, safe="")
print("Step 5 - Proxy URL-safe:", proxy_safe)
# This goes into: /proxy?url={proxy_safe}

# Step 6: When hls.js requests the proxy URL
# The M3U8 from step 5 returns relative URLs like: /proxy?url=aHR0cDovLzY3NmFk...
# hls.js resolves these relative to the player page URL
# Since player page is at /player?url=..., the relative URL resolves incorrectly

print("\n=== Testing proxy call ===")
import requests
full_proxy = f"http://127.0.0.1:9529/proxy?url={proxy_safe}"
r = requests.get(full_proxy, timeout=5)
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type')}")
print(f"Body (first 400): {r.text[:400]}")

# Check if URLs in M3U8 are relative or absolute
if "/proxy?url=" in r.text:
    import re
    urls = re.findall(r'/proxy\?url=[^\s"\'#,]+', r.text)
    print(f"\nFound {len(urls)} relative proxy URLs in M3U8")
    if urls:
        print("Example:", urls[0][:80])
