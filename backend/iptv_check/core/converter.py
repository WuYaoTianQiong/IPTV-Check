import re
import os
import logging
from typing import List

from iptv_check.models.channel import Channel

logger = logging.getLogger(__name__)


class FormatConverter:
    @staticmethod
    def m3u_to_txt(m3u_content: str) -> str:
        lines = []
        name = "N/A"
        for line in m3u_content.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF:"):
                match = re.search(r",(.+)", line)
                name = match.group(1).strip() if match else "N/A"
            elif "://" in line and not line.startswith("#"):
                lines.append(f"{name},{line}")
                name = "N/A"
        return "\n".join(lines)

    @staticmethod
    def txt_to_m3u(txt_content: str) -> str:
        lines = ["#EXTM3U"]
        name = "N/A"
        for line in txt_content.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF:"):
                match = re.search(r",(.+)", line)
                name = match.group(1).strip() if match else "N/A"
                lines.append(line)
            elif "," in line:
                parts = line.split(",", 1)
                if "://" in parts[-1]:
                    lines.append(f"#EXTINF:-1,{parts[0].strip()}")
                    lines.append(parts[1].strip())
                    name = "N/A"
            elif "://" in line and not line.startswith("#"):
                lines.append(f"#EXTINF:-1,{name}")
                lines.append(line)
                name = "N/A"
        return "\n".join(lines)

    @staticmethod
    def convert_file(input_path: str, output_format: str) -> str:
        with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_dir = os.path.dirname(input_path)
        output_path = os.path.join(output_dir, f"{base_name}_converted.{output_format}")

        with open(output_path, "w", encoding="utf-8") as f:
            if output_format == "m3u":
                if content.strip().startswith("#EXTM3U"):
                    f.write(content)
                else:
                    f.write(FormatConverter.txt_to_m3u(content))
            elif output_format == "txt":
                if content.strip().startswith("#EXTM3U"):
                    f.write(FormatConverter.m3u_to_txt(content))
                else:
                    f.write(content)

        return output_path
