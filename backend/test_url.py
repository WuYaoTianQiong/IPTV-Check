import base64, urllib.parse

# The actual stream URL
stream_url = "http://hls.nntv.cn/nnlive/SLTV_A.m3u8"

# Current (WRONG) encoding in render_player_html:
encoded_wrong = base64.b64encode(stream_url.encode("utf-8")).decode("utf-8")
encoded_safe_wrong = urllib.parse.quote(encoded_wrong, safe="")
print("WRONG encoding:")
print(f"  Base64: {encoded_wrong}")
print(f"  URL-safe: {encoded_safe_wrong}")

# CORRECT encoding (no URL encoding needed for base64):
encoded_correct = base64.b64encode(stream_url.encode("utf-8")).decode("utf-8")
print("\nCORRECT encoding (base64 is URL-safe by default):")
print(f"  Base64: {encoded_correct}")

# The user's URL has:
user_base64 = "aHR0cCUzQSUyRiUyRmhscy5ubnR2LmNuJTJGbm5saXZlJTJGU0xUVl9BLm0zdTg="
print("\nUser's base64 decoded:", base64.b64decode(user_base64).decode())
print("^ This is a URL-encoded string, not a raw URL!")

# Let's also test with the app.py decoding logic
print("\n=== Testing app.py decoding logic ===")
decoded = base64.b64decode(user_base64).decode("utf-8")
print(f"After base64 decode: {decoded}")
stream_url = urllib.parse.unquote(decoded)
print(f"After unquote: {stream_url}")

# Now test proxy with correct encoding
proxy_url = urllib.parse.quote(base64.b64encode(stream_url.encode()).decode(), safe='')
print(f"\nProxy URL: /proxy?url={proxy_url}")
