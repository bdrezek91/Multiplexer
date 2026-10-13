"""Read-only Claude Pro dashboard contract (no PostgreSQL required)."""
from app.modules.documents.router import router, get_claude_usage
from app.modules.users import require_admin


class FakeQuery:
    def __init__(self):
        self.results=iter([3,1,2])
    def filter(self,*args):
        return self
    def count(self):
        return next(self.results)


class FakeSession:
    def __init__(self):
        self.q=FakeQuery()
    def query(self,*args):
        return self.q


def test_claude_usage_route_is_admin_only():
    route=next(r for r in router.routes if getattr(r,"path","")=="/documents/claude-usage")
    dependency_calls=[dep.call for dep in route.dependant.dependencies]
    assert require_admin in dependency_calls
    assert "GET" in route.methods


def test_claude_usage_returns_real_counts_without_fake_quota():
    result=get_claude_usage(session=FakeSession(),_admin=object())
    assert result["documents_done"]==3
    assert result["documents_error"]==1
    assert result["documents_waiting"]==2
    assert result["subscription_remaining"] is None
    assert result["pages_7d"]>=0
    assert result["plan"]=="Claude Pro"
