from typing import Optional, Any, Dict
from fastapi.responses import JSONResponse


class APIResponse:
    """统一 API 响应格式"""

    @staticmethod
    def success(data: Any = None, message: str = "操作成功", code: int = 200) -> JSONResponse:
        return JSONResponse(
            status_code=code,
            content={
                "success": True,
                "code": code,
                "message": message,
                "data": data,
            },
        )

    @staticmethod
    def error(message: str = "操作失败", code: int = 400, details: Optional[Dict] = None) -> JSONResponse:
        content = {
            "success": False,
            "code": code,
            "message": message,
        }
        if details:
            content["details"] = details
        return JSONResponse(status_code=code, content=content)

    @staticmethod
    def paginated(items: list, total: int, page: int, per_page: int) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "code": 200,
                "message": "操作成功",
                "data": {
                    "items": items,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page,
                },
            },
        )
