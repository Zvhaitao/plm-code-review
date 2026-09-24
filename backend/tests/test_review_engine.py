"""评审引擎测试:mock 模型客户端,验证 JSON 解析与空 diff 处理。"""
import json

from app.services.review_engine import run_claude_review


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_TextBlock(text)]


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.called_with = None

    def create(self, **kwargs):
        self.called_with = kwargs
        return _FakeMessage(self._text)


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def test_run_review_parses_json_findings():
    payload = {
        "summary": "发现一个空指针风险",
        "score": 80,
        "findings": [
            {
                "file_path": "app/foo.py",
                "line": 12,
                "severity": "error",
                "category": "正确性",
                "message": "可能的空指针",
                "suggestion": "增加 None 判断",
            }
        ],
    }
    client = _FakeClient(json.dumps(payload))
    result = run_claude_review("acme/demo", "fix bug", "diff --git a/foo b/foo\n+x = None\n", client=client)
    assert result.score == 80
    assert len(result.findings) == 1
    assert result.findings[0].severity == "error"
    assert "foo" in client.messages.called_with["messages"][0]["content"]


def test_run_review_tolerates_markdown_fence():
    payload = {"summary": "ok", "score": 90, "findings": []}
    client = _FakeClient("这是评审结果:\n```json\n" + json.dumps(payload) + "\n```\n谢谢")
    result = run_claude_review("acme/demo", "t", "diff x", client=client)
    assert result.score == 90
    assert result.findings == []


def test_empty_diff_shortcircuits():
    client = _FakeClient("{}")  # 不应被调用
    result = run_claude_review("acme/demo", "empty", "   ", client=client)
    assert result.score == 100
    assert result.findings == []
    assert client.messages.called_with is None
