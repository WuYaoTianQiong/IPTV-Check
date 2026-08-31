import os
import csv
import logging
from abc import ABC, abstractmethod
from typing import List
from datetime import datetime

from iptv_check.models.check_result import CheckResult

logger = logging.getLogger(__name__)


class ExportStrategy(ABC):
    @abstractmethod
    def export(self, results: List[CheckResult], path: str, **kwargs) -> str:
        pass


class M3uExporter(ExportStrategy):
    def export(self, results: List[CheckResult], path: str, **kwargs) -> str:
        local_isp = kwargs.get("local_isp", "未知")
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            f.write(f"# 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 本地网络: {local_isp}宽带\n\n")
            for r in results:
                if r.is_valid:
                    f.write(f"#EXTINF:-1,{r.channel.name}\n{r.channel.url}\n")
        return path


class TxtExporter(ExportStrategy):
    def export(self, results: List[CheckResult], path: str, **kwargs) -> str:
        with open(path, "w", encoding="utf-8") as f:
            for r in results:
                if not r.is_valid:
                    f.write(f"{r.channel.name},{r.channel.url} # 错误: {r.details}\n")
        return path


class CsvExporter(ExportStrategy):
    HEADERS = ["原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息"]

    def export(self, results: List[CheckResult], path: str, **kwargs) -> str:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.HEADERS)
            for r in results:
                writer.writerow(r.to_tree_values())
        return path


class ExcelExporter(ExportStrategy):
    HEADERS = ["原始序号", "来源文件", "频道名称", "URL", "状态", "延迟(ms)", "速度(KB/s)", "信息"]

    def export(self, results: List[CheckResult], path: str, **kwargs) -> str:
        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment, PatternFill
        except ImportError:
            logger.warning("openpyxl 未安装，跳过Excel导出")
            return ""

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "检测结果"

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        for col_idx, header in enumerate(self.HEADERS, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        for row_idx, r in enumerate(results, 2):
            values = r.to_tree_values()
            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                if val == "有效":
                    cell.font = Font(color="00B050")
                elif val == "无效":
                    cell.font = Font(color="FF0000")

        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 50)

        wb.save(path)
        return path


class ExportEngine:
    def __init__(self):
        self._strategies = {
            "m3u": M3uExporter(),
            "txt": TxtExporter(),
            "csv": CsvExporter(),
            "xlsx": ExcelExporter(),
        }

    def export(self, fmt: str, results: List[CheckResult], path: str, **kwargs) -> str:
        strategy = self._strategies.get(fmt)
        if not strategy:
            raise ValueError(f"不支持的导出格式: {fmt}")
        return strategy.export(results, path, **kwargs)

    def export_batch(self, formats: List[str], results: List[CheckResult],
                     export_dir: str, base_name: str, local_isp: str = "未知") -> List[str]:
        exported = []
        name_map = {
            "m3u": f"{base_name}_有效源.m3u",
            "txt": f"{base_name}_无效源.txt",
            "csv": f"{base_name}_检测结果.csv",
            "xlsx": f"{base_name}_检测结果.xlsx",
        }
        for fmt in formats:
            path = os.path.join(export_dir, name_map[fmt])
            result = self.export(fmt, results, path, local_isp=local_isp)
            if result:
                exported.append(result)
        return exported
