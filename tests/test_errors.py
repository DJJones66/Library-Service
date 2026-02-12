from app.errors import ErrorResponse, McpError


def test_error_response_serializes_details():
    error = ErrorResponse(code="PATH_TRAVERSAL", message="Nope", details={"path": ".."})

    assert error.to_dict() == {
        "code": "PATH_TRAVERSAL",
        "message": "Nope",
        "details": {"path": ".."},
    }


def test_mcp_error_defaults_details():
    exc = McpError("INVALID_TYPE", "Bad path")

    assert exc.error.to_dict() == {
        "code": "INVALID_TYPE",
        "message": "Bad path",
        "details": {},
    }
