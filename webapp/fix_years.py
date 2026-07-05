import os
import re

template_dir = r"c:\projects\Project_BPS\webapp\templates"

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith(".html"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Replace {{ variable.tahun_terbit }} with {{ variable.tahun_terbit|stringformat:"s" }}
            new_content = re.sub(r'(\{\{\s*[^}]*\.tahun_terbit)(\s*\}\})', r'\1|stringformat:"s"\2', content)
            
            # Replace {{ p.tahun_terbit }} specifically
            new_content = re.sub(r'(\{\{\s*p\.tahun_terbit)(\s*\}\})', r'\1|stringformat:"s"\2', new_content)
            
            # Replace {{ pub.tahun_terbit }}
            new_content = re.sub(r'(\{\{\s*pub\.tahun_terbit)(\s*\}\})', r'\1|stringformat:"s"\2', new_content)
            
            # Replace {{ a.tahun|default:"-" }} with |stringformat:"s"
            new_content = re.sub(r'(\{\{\s*a\.tahun\|default:"-"\s*)(\}\})', r'\1|stringformat:"s"\2', new_content)
            
            # Replace {{ k.tahun }}
            new_content = re.sub(r'(\{\{\s*k\.tahun)(\s*\}\})', r'\1|stringformat:"s"\2', new_content)

            if new_content != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print("Updated", file)
