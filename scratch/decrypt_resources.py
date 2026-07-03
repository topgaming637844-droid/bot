import base64
import json
import re
from pathlib import Path

def decrypt_resource(resource_data, config_settings):
    # 1. Reverse resource_data and filter base64 chars
    reversed_data = resource_data[::-1]
    reversed_data = re.sub(r'[^A-Za-z0-9+/=]', '', reversed_data)
    
    # 2. Calculate parameter offset
    index_key_bytes = base64.b64decode(config_settings["k"])
    index_key = index_key_bytes.decode("utf-8")
    param_offset = config_settings["d"][int(index_key)]
    
    # 3. Base64 decode and slice
    decoded_bytes = base64.b64decode(reversed_data)
    if param_offset > 0:
        decoded_bytes = decoded_bytes[:-param_offset]
    decoded_resource = decoded_bytes.decode("utf-8")
    
    # 4. framework hash (apiKey)
    framework_hash = "23a97133-caf3-4eb4-9466-93d0a4ff8198"
    if re.match(r"^https://yonaplay\.net/embed\.php\?id=\d+$", decoded_resource):
        return decoded_resource + "&apiKey=" + framework_hash
    return decoded_resource

def main():
    script_path = Path("c:/Users/monsm/OneDrive/Desktop/BOT/scratch/script14.js")
    with open(script_path, "r", encoding="utf-8") as f:
        js_code = f.read()
        
    # Extract _zX and _zK via regex
    zx_match = re.search(r'var _zX="([^"]+)"', js_code)
    zk_match = re.search(r'var _zK="([^"]+)"', js_code)
    
    if not zx_match or not zk_match:
        print("Could not find _zX or _zK in script code")
        return
        
    zx = zx_match.group(1)
    zk = zk_match.group(1)
    
    resources = json.loads(base64.b64decode(zx).decode("utf-8"))
    configs = json.loads(base64.b64decode(zk).decode("utf-8"))
    
    print(f"Loaded {len(resources)} resources and {len(configs)} configs.")
    
    for idx, (res, conf) in enumerate(zip(resources, configs)):
        decrypted = decrypt_resource(res, conf)
        print(f"Decrypted Server {idx+1}: {decrypted}")

if __name__ == "__main__":
    main()
