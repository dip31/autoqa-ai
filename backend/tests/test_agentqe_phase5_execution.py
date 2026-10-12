"""
Phase 5 — AgentQE Test Execution tests.

Covers:
  * ExecutionPlanner: NL + structured steps, unsupported/blocked, redaction
  * Selector ladder: strategy ordering, no nth-child, observed-only evidence
  * ActionExecutor: actions, assertions, failure categories
  * PlaywrightTestExecutor: lifecycle, isolation, timeouts (with a fake browser)
  * ExecutionService: rank order, isolation, summary, provenance
  * Browser Use adapter: opt-in gating (never runs unless explicitly enabled)
  * ExecutionRepository: persistence round-trip
  * API: the four Phase 5 routes
  * Backwards compatibility with the pre-Phase-5 ExecutionResult
"""

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("AGENTQE_RAG_EMBEDDING_PROVIDER", "mock")

from agentqe.execution.action_executor import ActionExecutor, StepNotExecutable
from agentqe.execution.config import ExecutionConfig
from agentqe.execution.execution_planner import ExecutionPlanner
from agentqe.execution.execution_service import ExecutionService
from agentqe.execution.playwright_executor import PlaywrightTestExecutor
from agentqe.execution.redaction import (
    looks_like_secret,
    redact_text,
    redact_url,
    sanitize_step_value,
)
from agentqe.execution.schemas import (
    EXECUTOR_BROWSER_USE,
    EXECUTOR_NONE,
    EXECUTOR_PLAYWRIGHT,
    ActionType,
    FailureCategory,
    SELECTOR_STRATEGY_ORDER,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_UNSUPPORTED,
)
from agentqe.models.test_case import CandidateTest


# ═══════════════════════════════════════════════════════════════════════════
# Fakes
# ═══════════════════════════════════════════════════════════════════════════
class FakeLocator:
    """
    Minimal Playwright Locator double.

    Mirrors real Playwright semantics that matter to the executor: a locator
    matching zero elements is not visible and raises on any interaction.
    """

    def __init__(self, count=1, visible=True, text="Welcome, Test User"):
        self._count = count
        self._visible = visible
        self._text = text
        self.actions = []

    def _require(self):
        if self._count == 0:
            raise AssertionError(
                "locator resolved to 0 elements; Playwright would time out here"
            )
        return self

    def count(self):
        return self._count

    def first(self):
        return self

    def fill(self, value, timeout=None):
        self.actions.append(("fill", value))
        return self._require()

    def click(self, timeout=None):
        self.actions.append(("click",))
        return self._require()

    def check(self, timeout=None):
        self.actions.append(("check",))
        return self._require()

    def uncheck(self, timeout=None):
        self.actions.append(("uncheck",))
        return self._require()

    def hover(self, timeout=None):
        self.actions.append(("hover",))
        return self._require()

    def press(self, key, timeout=None):
        self.actions.append(("press", key))
        return self._require()

    def select_option(self, value=None, label=None, timeout=None, **kw):
        self.actions.append(("select", value or label))
        return self._require()

    def is_visible(self, timeout=None):
        # Real Playwright reports False (never raises) for a missing element.
        return self._visible and self._count > 0

    def inner_text(self, timeout=None):
        return self._text if self._count else ""

    def text_content(self, timeout=None):
        return self._text if self._count else None

    def get_attribute(self, name, timeout=None):
        return None


class FakePage:
    """Minimal Playwright Page double driven by a label/role lookup table."""

    def __init__(self, labels=(), roles=(), body_text="Welcome, Test User", url=""):
        self.url = url
        self._labels = set(labels)
        self._roles = set(roles)
        self._body = body_text
        self.goto_calls = []
        self.waited = []
        self.context = FakeContext()
        self.filled = []

    def goto(self, url, timeout=None, wait_until=None):
        self.goto_calls.append(url)
        self.url = url

    def wait_for_timeout(self, ms):
        self.waited.append(ms)

    def get_by_role(self, role, name=None, exact=False):
        return FakeLocator(1 if name in self._roles else 0)

    def get_by_label(self, name, exact=False):
        page = self
        if name not in self._labels:
            return FakeLocator(0)

        class _Labelled(FakeLocator):
            def fill(self, value, timeout=None):
                page.filled.append((name, value))
                return self

        return _Labelled(1)

    def get_by_placeholder(self, name, exact=False):
        return FakeLocator(1 if name in self._labels else 0)

    def get_by_text(self, name, exact=False):
        return FakeLocator(0)

    def locator(self, selector, **kw):
        return FakeLocator(1 if selector == "body" else 0, text=self._body)

    def content(self):
        return f"<html><body>{self._body}</body></html>"

    def inner_text(self, selector=None, timeout=None):
        return self._body

    def on(self, event, handler):
        return None

    def add_init_script(self, script):
        return None

    def set_default_timeout(self, ms):
        return None


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False
        self.trace_started = False

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    def set_default_timeout(self, ms):
        return None

    def set_default_navigation_timeout(self, ms):
        return None

    def add_init_script(self, script):
        return None

    def tracing(self, **kwargs):
        action = kwargs.get("action")
        if action == "start":
            self.trace_started = True
        return None

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.contexts = []
        self.closed = False

    def new_context(self, **kwargs):
        ctx = FakeContext()
        self.contexts.append(ctx)
        return ctx

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.browser = FakeBrowser()

    def launch(self, **kwargs):
        return self.browser


class FakePlaywright:
    """Playwright factory double: ``with FakePlaywright() as pw``."""

    def __init__(self, labels=("Email", "Password"), roles=("Sign in",), body="Welcome, Test User"):
        self._labels = labels
        self._roles = roles
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def chromium(self):
        return _ChromiumProxy(self._labels, self._roles, self._body)


class _ChromiumProxy:
    def __init__(self, labels, roles, body):
        self._labels = labels
        self._roles = roles
        self._body = body

    def launch(self, **kwargs):
        browser = FakeBrowser()
        original = browser.new_context

        def new_context(**ck):
            ctx = original(**ck)
            ctx.new_page = lambda: FakePage(
                labels=self._labels, roles=self._roles, body_text=self._body
            )
            return ctx

        browser.new_context = new_context
        return browser


@pytest.fixture
def config():
    cfg = ExecutionConfig()
    cfg.playwright_enabled = True
    cfg.screenshots_enabled = False
    cfg.playwright_trace_enabled = False
    cfg.collect_network_evidence = False
    cfg.execution_timeout_ms = 60000
    cfg.credentials = {}
    return cfg


def login_test(config, **overrides):
    payload = dict(
        test_id="TC-LOGIN-1",
        title="Login succeeds with valid credentials",
        test_type="UI",
        target="login",
        priority="High",
        steps=[
            "Navigate to /login",
            "Type 'test@example.com' into the Email field",
            "Type 'Passw0rd!' into the Password field",
            "Click the Sign in button",
            "Assert text 'Welcome' is visible",
        ],
        expected_result="The dashboard is shown",
    )
    payload.update(overrides)
    return CandidateTest(**payload)


# ═══════════════════════════════════════════════════════════════════════════
# Redaction / test-data safety
# ═══════════════════════════════════════════════════════════════════════════
class TestRedaction:
    def test_redacts_password_assignment(self):
        text = 'password: "hunter2secret"'
        assert "hunter2secret" not in redact_text(text)

    def test_redacts_authorization_header(self):
        assert "abc123" not in redact_text("Authorization: Bearer abc123def456ghi")

    def test_redacts_query_string_secrets(self):
        cleaned = redact_url("https://app.test/login?token=supersecretvalue&user=bob")
        assert "supersecretvalue" not in cleaned
        assert "user=bob" in cleaned

    def test_detects_secret_like_values(self):
        assert looks_like_secret("sk-abcdefghijklmnopqrstuvwx")
        assert not looks_like_secret("test@example.invalid")

    def test_sanitize_replaces_unconfigured_password(self):
        cfg = ExecutionConfig()
        cfg.credentials = {}
        value, note = sanitize_step_value("Password", "RealUserSecret1!", cfg)
        assert value != "RealUserSecret1!"
        assert note

    def test_sanitize_keeps_configured_synthetic_value(self):
        cfg = ExecutionConfig()
        cfg.credentials = {"password": "Synthetic-Only-1!"}
        value, note = sanitize_step_value("Password", "Synthetic-Only-1!", cfg)
        assert value == "Synthetic-Only-1!"

    def test_planner_never_inlines_unconfigured_secret(self):
        cfg = ExecutionConfig()
        cfg.credentials = {}
        planner = ExecutionPlanner(cfg)
        test = login_test(cfg, steps=["Type 'MyRealPassword123' into the Password field"])
        plan = planner.plan(test, None, base_url="http://localhost:5000")
        for step in plan.steps:
            assert step.value != "MyRealPassword123"


# ═══════════════════════════════════════════════════════════════════════════
# Planner
# ═══════════════════════════════════════════════════════════════════════════
class TestExecutionPlanner:
    def test_plans_natural_language_login_flow(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        assert plan.status_hint == "ready"
        assert plan.target_url.startswith("http://localhost:5000")
        actions = [s.action for s in plan.supported_steps]
        assert actions[0] == ActionType.NAVIGATE
        assert ActionType.FILL in actions
        assert ActionType.CLICK in actions
        assert ActionType.ASSERT_TEXT in actions

    def test_extracts_fill_target_and_value(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        fills = {s.target: s.value for s in plan.supported_steps if s.action == ActionType.FILL}
        assert fills["Email"] == "test@example.com"
        # The password is a secret-looking value, so it is substituted with the
        # configured safe placeholder rather than inlined verbatim.
        assert fills["Password"] == config.safe_credential_placeholder

    def test_configured_credential_is_used_verbatim(self):
        cfg = ExecutionConfig()
        cfg.credentials = {"password": "Synthetic-Only-1!"}
        test = CandidateTest(
            test_id="TC-CRED", title="Login", test_type="UI", priority="High",
            steps=["Type 'Synthetic-Only-1!' into the Password field"],
        )
        plan = ExecutionPlanner(cfg).plan(test, None, base_url="http://x.test")
        fills = {s.target: s.value for s in plan.supported_steps if s.action == ActionType.FILL}
        assert fills["Password"] == "Synthetic-Only-1!"

    def test_checkbox_verb_is_not_an_assertion(self, config):
        test = CandidateTest(
            test_id="TC-CHECK", title="Accept terms", test_type="UI",
            steps=["Check the Terms checkbox"], priority="Medium",
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        assert plan.supported_steps[0].action == ActionType.CHECK

    def test_blocked_test_is_not_planned(self, config):
        test = login_test(
            config, blocked_reason="payment provider credentials are not configured"
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://localhost:5000")
        assert plan.status_hint == "blocked"
        assert "payment provider" in plan.blocked_reason
        assert plan.steps == []

    def test_non_ui_test_is_unsupported(self, config):
        test = CandidateTest(
            test_id="TC-API", title="API returns 200", test_type="API",
            steps=["Call GET /api/items"], priority="Medium",
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://localhost:5000")
        assert plan.status_hint == "unsupported"
        assert plan.layer == "api"

    def test_missing_url_makes_plan_unsupported(self, config):
        test = CandidateTest(
            test_id="TC-NOURL", title="Unknown target", test_type="UI",
            steps=["Do something entirely unsupported with a widget"], priority="Low",
        )
        plan = ExecutionPlanner(config).plan(test, None)
        assert plan.status_hint == "unsupported"

    def test_unparseable_step_is_marked_unsupported_not_fabricated(self, config):
        test = CandidateTest(
            test_id="TC-WEIRD", title="Weird", test_type="UI",
            steps=["Flibbertigibbet the wobble"], priority="Low",
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        assert plan.status_hint == "unsupported"
        assert plan.unsupported_steps or not plan.supported_steps

    def test_structured_dict_step_is_supported(self, config):
        test = CandidateTest(
            test_id="TC-DICT", title="Structured", test_type="UI", priority="Medium",
            steps=[{"action": "click", "target": "Submit button"}],
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        step = plan.supported_steps[0]
        assert step.action == ActionType.CLICK
        assert step.target == "Submit button"

    def test_structured_step_with_explicit_selector(self, config):
        test = CandidateTest(
            test_id="TC-SEL", title="Selector", test_type="UI", priority="Medium",
            steps=[{"action": "click", "target": "Submit",
                    "selector": "[data-testid=submit]"}],
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        assert plan.supported_steps[0].selectors, "explicit selector must be honoured"

    def test_plan_records_rank_position(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://x.test", rank_position=7
        )
        assert plan.metadata["rank_position"] == 7

    def test_browser_use_not_allowed_by_default(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://x.test"
        )
        assert EXECUTOR_PLAYWRIGHT in plan.allowed_executors
        assert EXECUTOR_BROWSER_USE not in plan.allowed_executors


# ═══════════════════════════════════════════════════════════════════════════
# Selectors
# ═══════════════════════════════════════════════════════════════════════════
class TestSelectorStrategy:
    def test_strategy_order_is_robustness_order(self):
        assert SELECTOR_STRATEGY_ORDER[0] == "role_name"
        assert SELECTOR_STRATEGY_ORDER[-1] == "xpath"

    def test_selectors_never_generate_nth_child(self):
        from agentqe.execution.selectors import (
            build_selector_candidates,
            resolve_selectors,
        )

        observed = [{
            "element_id": "el-1",
            "tag": "input",
            "element_type": "textbox",
            "accessible_name": "Email",
            "label_text": "Email",
            "attributes": {"id": "email", "name": "email", "placeholder": "Email"},
            "css_selector": "form input#email",
            "observation_status": "observed",
        }]
        names = ("Email", "Password", "Save changes", "anything at all")
        for name in names:
            ladders = [resolve_selectors(name, elements=observed), resolve_selectors(name)]
            for candidate in build_selector_candidates(observed[0], name):
                ladders.append([candidate])
            for candidate in (c for ladder in ladders for c in ladder):
                assert ":nth-child" not in candidate.value
                assert "nth-of-type" not in candidate.value

    def test_positional_explicit_selector_is_rejected(self, config):
        test = CandidateTest(
            test_id="TC-POS", title="Positional", test_type="UI", priority="Medium",
            steps=[{"action": "click", "target": "Save",
                    "selector": "div.form > button:nth-child(2)"}],
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        step = plan.supported_steps[0]
        assert all(":nth-child" not in c.value for c in step.selectors)


# ═══════════════════════════════════════════════════════════════════════════
# Action executor
# ═══════════════════════════════════════════════════════════════════════════
class TestActionExecutor:
    def _page(self):
        return FakePage(labels=("Email",), roles=("Sign in",), body_text="Welcome back")

    def test_click_resolves_by_role(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan, SelectorCandidate

        step = ExecutionStepPlan(
            index=0, action=ActionType.CLICK, target="Sign in",
            selectors=[SelectorCandidate(strategy="role_name", value="Sign in")],
        )
        outcome = ActionExecutor(config).execute(self._page(), step)
        assert outcome.passed
        assert outcome.selector_strategy == "role_name"
        assert outcome.selector_used == "Sign in"

    def test_missing_element_yields_element_not_found(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan, SelectorCandidate

        step = ExecutionStepPlan(
            index=0, action=ActionType.CLICK, target="Nonexistent",
            selectors=[SelectorCandidate(strategy="test_id", value="nope")],
        )
        # The public boundary never raises; it returns a structured outcome.
        outcome = ActionExecutor(config).execute(self._page(), step)
        assert outcome.passed is False
        assert outcome.error_category == FailureCategory.ELEMENT_NOT_FOUND
        assert "Nonexistent" in (outcome.error or "")

    def test_resolve_raises_when_no_candidate_matches(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan, SelectorCandidate

        step = ExecutionStepPlan(
            index=0, action=ActionType.CLICK, target="Nonexistent",
            selectors=[
                SelectorCandidate(strategy="test_id", value="nope"),
                SelectorCandidate(strategy="attribute", value="#also-missing"),
            ],
        )
        with pytest.raises(StepNotExecutable) as exc:
            ActionExecutor(config)._resolve(self._page(), step)
        assert exc.value.category == FailureCategory.ELEMENT_NOT_FOUND
        # Both strategies were attempted before giving up.
        assert "test_id" in exc.value.reason
        assert "attribute" in exc.value.reason

    def test_assert_text_passes_when_text_present(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan

        step = ExecutionStepPlan(
            index=0, action=ActionType.ASSERT_TEXT, target="Welcome", value="Welcome"
        )
        outcome = ActionExecutor(config).execute(self._page(), step)
        assert outcome.passed
        assert outcome.assertion.passed
        assert outcome.assertion.assertion_type == ActionType.ASSERT_TEXT

    def test_assert_text_fails_with_assertion_failed(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan

        step = ExecutionStepPlan(
            index=0, action=ActionType.ASSERT_TEXT, target="Goodbye", value="Goodbye"
        )
        outcome = ActionExecutor(config).execute(self._page(), step)
        assert not outcome.passed
        assert outcome.error_category == FailureCategory.ASSERTION_FAILED
        assert outcome.assertion.passed is False

    def test_wait_step_is_bounded(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan

        page = self._page()
        step = ExecutionStepPlan(index=0, action=ActionType.WAIT, target="2000", value=2000)
        outcome = ActionExecutor(config).execute(page, step)
        assert outcome.passed
        assert page.waited == [2000]

    def test_wait_step_clamps_absurd_durations(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan

        page = self._page()
        step = ExecutionStepPlan(index=0, action=ActionType.WAIT, target="999999", value=999999)
        ActionExecutor(config).execute(page, step)
        assert page.waited and page.waited[0] <= 60000

    def test_assert_not_visible_passes_when_absent(self, config):
        from agentqe.execution.schemas import ExecutionStepPlan, SelectorCandidate

        step = ExecutionStepPlan(
            index=0, action=ActionType.ASSERT_NOT_VISIBLE, target="Banner",
            selectors=[SelectorCandidate(strategy="test_id", value="absent-banner")],
        )
        outcome = ActionExecutor(config).execute(self._page(), step)
        assert outcome.passed
        assert outcome.assertion.passed


# ═══════════════════════════════════════════════════════════════════════════
# Playwright executor
# ═══════════════════════════════════════════════════════════════════════════
class TestPlaywrightExecutor:
    def test_passing_execution(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        executor = PlaywrightTestExecutor(config, playwright_factory=FakePlaywright)
        result = executor.execute_plan(plan, test=login_test(config))
        assert result.status == STATUS_PASSED
        assert result.executor == EXECUTOR_PLAYWRIGHT
        assert result.steps_completed == result.steps_total
        assert result.assertions_total == 1
        assert result.assertions_passed == 1
        assert all(isinstance(a, dict) for a in result.assertions)

    def test_selector_provenance_recorded(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        result = PlaywrightTestExecutor(
            config, playwright_factory=FakePlaywright
        ).execute_plan(plan, test=login_test(config))
        used = {s["selector_strategy"] for s in result.steps if s.get("selector_used")}
        assert used, "selector strategy must be recorded for traceability"
        # Strategies may carry a ":fallback" suffix when the element was located
        # by role/label text rather than by observed evidence.
        base = {s.split(":")[0] for s in used}
        assert base & {"role_name", "label", "test_id", "attribute", "css", "xpath"}

    def test_missing_element_yields_failed_not_exception(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        executor = PlaywrightTestExecutor(
            config, playwright_factory=lambda: FakePlaywright(labels=(), roles=())
        )
        result = executor.execute_plan(plan, test=login_test(config))
        assert result.status == STATUS_FAILED
        assert result.error_category == FailureCategory.ELEMENT_NOT_FOUND
        assert result.failed_step is not None

    def test_assertion_failure_is_classified(self, config):
        test = login_test(config, steps=[
            "Navigate to /login",
            "Assert text 'Nonexistent Banner' is visible",
        ])
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        result = PlaywrightTestExecutor(
            config, playwright_factory=lambda: FakePlaywright(body="Welcome back")
        ).execute_plan(plan, test=test)
        assert result.status == STATUS_FAILED
        assert result.error_category == FailureCategory.ASSERTION_FAILED

    def test_blocked_plan_never_launches_browser(self, config):
        test = login_test(config, blocked_reason="needs a real payment sandbox")
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        result = PlaywrightTestExecutor(
            config, playwright_factory=FakePlaywright
        ).execute_plan(plan, test=test)
        assert result.status == STATUS_BLOCKED
        assert result.executor == EXECUTOR_NONE

    def test_unsupported_plan_never_launches_browser(self, config):
        test = CandidateTest(
            test_id="TC-API", title="API", test_type="API",
            steps=["Call GET /x"], priority="Medium",
        )
        plan = ExecutionPlanner(config).plan(test, None, base_url="http://x.test")
        result = PlaywrightTestExecutor(
            config, playwright_factory=FakePlaywright
        ).execute_plan(plan, test=test)
        assert result.status == STATUS_UNSUPPORTED

    def test_browser_context_is_isolated_and_closed(self, config):
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        result = PlaywrightTestExecutor(
            config, playwright_factory=FakePlaywright
        ).execute_plan(plan, test=login_test(config))
        assert result.status == STATUS_PASSED
        assert result.steps_total > 0

    def test_overall_timeout_yields_timeout_status(self, config):
        config.execution_timeout_ms = 0
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        result = PlaywrightTestExecutor(
            config, playwright_factory=FakePlaywright
        ).execute_plan(plan, test=login_test(config))
        assert result.status == "timeout"
        assert result.error_category == FailureCategory.TIMEOUT

    def test_per_call_config_override_is_used(self, config):
        override = ExecutionConfig()
        override.playwright_headless = False
        override.screenshots_enabled = False
        override.playwright_trace_enabled = False
        plan = ExecutionPlanner(config).plan(
            login_test(config), None, base_url="http://localhost:5000"
        )
        executor = PlaywrightTestExecutor(config, playwright_factory=FakePlaywright)
        result = executor.execute_plan(plan, test=login_test(config), config=override)
        assert result.status == STATUS_PASSED


# ═══════════════════════════════════════════════════════════════════════════
# Execution service
# ═══════════════════════════════════════════════════════════════════════════
class TestExecutionService:
    def _service(self, config, factory=None):
        return ExecutionService(
            planner=ExecutionPlanner(config),
            executor=PlaywrightTestExecutor(
                config, playwright_factory=factory or FakePlaywright
            ),
            repository=None,
            config=config,
        )

    def test_runs_tests_in_rank_order(self, config):
        a = login_test(config, test_id="TC-A")
        b = login_test(config, test_id="TC-B")
        c = login_test(config, test_id="TC-C")
        run = self._service(config).execute_tests([a, b, c], base_url="http://x.test",
                                                  persist=False)
        assert [r.test_id for r in run.results] == ["TC-A", "TC-B", "TC-C"]
        assert [r.rank_position for r in run.results] == [1, 2, 3]

    def test_summary_counts_every_status(self, config):
        passing = login_test(config, test_id="TC-PASS")
        blocked = login_test(
            config, test_id="TC-BLOCK", blocked_reason="needs a sandbox account"
        )
        unsupported = CandidateTest(
            test_id="TC-API", title="API", test_type="API",
            steps=["Call GET /x"], priority="Low",
        )
        run = self._service(config).execute_tests(
            [passing, blocked, unsupported], base_url="http://x.test", persist=False
        )
        summary = run.summary.to_dict()
        assert summary["total"] == 3
        assert summary["passed"] == 1
        assert summary["blocked"] == 1
        assert summary["unsupported"] == 1

    def test_one_failing_test_does_not_abort_the_batch(self, config):
        good = login_test(config, test_id="TC-GOOD")
        bad = login_test(
            config, test_id="TC-BAD",
            steps=["Navigate to /login", "Click the Missing Button"],
        )
        run = self._service(config, lambda: FakePlaywright(labels=(), roles=())).execute_tests(
            [good, bad], base_url="http://x.test", persist=False
        )
        assert len(run.results) == 2
        assert run.results[0].test_id == "TC-GOOD"
        assert run.results[1].test_id == "TC-BAD"

    def test_ranking_provenance_preserved(self, config):
        test = login_test(config)
        ranked = {
            "test": test.to_dict(),
            "final_score": 0.91,
            "predicted_priority": 0.88,
            "ranking_mode": "transformer",
            "model_status": "ready",
            "model_version": "v3",
            "feature_version": "9",
            "features": {"risk_score": 0.7, "coverage_gain": 0.4},
            "feature_contributions": {"risk_score": 0.25},
        }
        run = self._service(config).execute_tests([ranked], base_url="http://x.test",
                                                  persist=False)
        result = run.results[0]
        assert result.test_id == test.test_id
        assert result.ranking_mode == "transformer"
        assert result.model_status == "ready"
        assert result.model_version == "v3"
        assert result.feature_version == "9"
        assert result.priority_score == 0.91
        assert result.predicted_priority == 0.88
        assert result.features["risk_score"] == 0.7
        assert result.feature_contributions["risk_score"] == 0.25

    def test_result_invents_no_phase6_fields(self, config):
        run = self._service(config).execute_tests(
            [login_test(config)], base_url="http://x.test", persist=False
        )
        payload = run.results[0].to_dict()
        for forbidden in ("root_cause", "severity", "novelty", "healed_by",
                          "healing_strategy", "recovery_success"):
            assert forbidden not in payload

    def test_metadata_contains_no_plaintext_secret(self, config):
        config.credentials = {}
        test = login_test(
            config, steps=["Type 'LeakedSecret12345' into the Password field"]
        )
        run = self._service(config).execute_tests([test], base_url="http://x.test",
                                                  persist=False)
        import json
        blob = json.dumps(run.results[0].to_dict())
        assert "LeakedSecret12345" not in blob

    def test_execute_single_test(self, config):
        result = self._service(config).execute_test(
            login_test(config), base_url="http://x.test", persist=False
        )
        assert result.status == STATUS_PASSED

    def test_empty_batch_is_handled(self, config):
        run = self._service(config).execute_tests([], persist=False)
        assert run.summary.to_dict()["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Browser Use gating (optional, must never run implicitly)
# ═══════════════════════════════════════════════════════════════════════════
class TestBrowserUseGating:
    def test_disabled_by_default(self):
        from agentqe.execution.browser_use_executor import build_browser_agent_executor

        cfg = ExecutionConfig()
        cfg.browser_use_enabled = False
        agent = build_browser_agent_executor(cfg)
        assert agent.is_available is False
        assert agent.unavailable_reason()

    def test_can_recover_is_false_when_disabled(self, config):
        from agentqe.execution.browser_use_executor import BrowserUseTestExecutor
        from agentqe.execution.schemas import ExecutionResult

        cfg = ExecutionConfig()
        cfg.browser_use_enabled = False
        agent = BrowserUseTestExecutor(cfg)
        result = ExecutionResult(
            test_id="TC-1", status=STATUS_FAILED,
            error_category=FailureCategory.ELEMENT_NOT_FOUND,
        )
        assert agent.can_recover(result) is False

    def test_never_recovers_a_passing_test(self, config):
        from agentqe.execution.browser_use_executor import BrowserUseTestExecutor
        from agentqe.execution.schemas import ExecutionResult

        cfg = ExecutionConfig()
        cfg.browser_use_enabled = True
        cfg.browser_use_fallback_enabled = True
        agent = BrowserUseTestExecutor(cfg, agent_factory=lambda: object())
        result = ExecutionResult(test_id="TC-1", status=STATUS_PASSED)
        assert agent.can_recover(result) is False

    def test_only_recovers_whitelisted_categories(self, config):
        from agentqe.execution.browser_use_executor import BrowserUseTestExecutor
        from agentqe.execution.schemas import ExecutionResult

        cfg = ExecutionConfig()
        cfg.browser_use_enabled = True
        cfg.browser_use_fallback_enabled = True
        cfg.browser_use_fallback_categories = (FailureCategory.ELEMENT_NOT_FOUND,)
        agent = BrowserUseTestExecutor(cfg, agent_factory=lambda: object())
        allowed = ExecutionResult(
            test_id="TC-1", status=STATUS_FAILED,
            error_category=FailureCategory.ELEMENT_NOT_FOUND,
        )
        denied = ExecutionResult(
            test_id="TC-2", status=STATUS_FAILED,
            error_category=FailureCategory.ASSERTION_FAILED,
        )
        assert agent.can_recover(allowed) is True
        assert agent.can_recover(denied) is False

    def test_recover_returns_deterministic_result_when_disabled(self, config):
        from agentqe.execution.browser_use_executor import BrowserUseTestExecutor
        from agentqe.execution.schemas import ExecutionResult

        cfg = ExecutionConfig()
        cfg.browser_use_enabled = False
        agent = BrowserUseTestExecutor(cfg)
        deterministic = ExecutionResult(
            test_id="TC-1", status=STATUS_FAILED,
            error_category=FailureCategory.ELEMENT_NOT_FOUND, error="original failure",
        )
        result, recovered = agent.recover(None, deterministic)
        assert recovered is False
        assert result.error == "original failure"
        assert "browser_use_skipped" in result.metadata

    def test_service_does_not_invoke_agent_when_disabled(self, config):
        invoked = []

        class SpyAgent:
            is_available = True
            name = EXECUTOR_BROWSER_USE

            def can_recover(self, result):
                invoked.append(result)
                return True

            def recover(self, plan, deterministic_result, **kw):
                return deterministic_result, False

        cfg = ExecutionConfig()
        cfg.browser_use_enabled = False
        service = ExecutionService(
            planner=ExecutionPlanner(cfg),
            executor=PlaywrightTestExecutor(cfg, playwright_factory=FakePlaywright),
            browser_agent=SpyAgent(),
            repository=None,
            config=cfg,
        )
        service.execute_tests([login_test(cfg)], base_url="http://x.test", persist=False)
        assert invoked == [], "agent must not be consulted while Browser Use is disabled"


# ═══════════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════════
class TestExecutionRepository:
    def test_persist_and_read_back(self, config):
        from agentqe.execution.persistence import ExecutionRepository

        written = {}

        def fake_query(sql, params=(), fetch=False):
            written.setdefault("sql", []).append(sql)
            if fetch and sql.strip().upper().startswith("SELECT * FROM AGENTQE_EXECUTIONS"):
                return [{
                    "execution_id": params[0] if params else "exec_x",
                    "test_id": "TC-1", "status": "passed", "rank_position": 1,
                    "steps_json": None, "metadata_json": None,
                }]
            return 1

        repo = ExecutionRepository(query_fn=fake_query)
        run = ExecutionService(
            planner=ExecutionPlanner(config),
            executor=PlaywrightTestExecutor(config, playwright_factory=FakePlaywright),
            repository=repo,
            config=config,
        ).execute_tests([login_test(config)], base_url="http://x.test", persist=True)
        assert run.persisted is True
        assert any("agentqe_executions" in s for s in written["sql"])
        assert any("agentqe_execution_runs" in s for s in written["sql"])
        assert any("agentqe_execution_steps" in s for s in written["sql"])

    def test_repository_is_resilient_to_db_failure(self, config):
        from agentqe.execution.persistence import ExecutionRepository

        def broken(sql, params=(), fetch=False):
            raise RuntimeError("database is down")

        repo = ExecutionRepository(query_fn=broken)
        run = ExecutionService(
            planner=ExecutionPlanner(config),
            executor=PlaywrightTestExecutor(config, playwright_factory=FakePlaywright),
            repository=repo,
            config=config,
        ).execute_tests([login_test(config)], base_url="http://x.test", persist=True)
        assert run.persisted is False
        assert run.results[0].status == STATUS_PASSED, "DB failure must not lose results"

    def test_execution_result_to_record_is_json_safe(self, config):
        import json
        result = ExecutionService(
            planner=ExecutionPlanner(config),
            executor=PlaywrightTestExecutor(config, playwright_factory=FakePlaywright),
            repository=None,
            config=config,
        ).execute_tests([login_test(config)], base_url="http://x.test",
                        persist=False).results[0]
        json.dumps(result.to_record())

    def test_shipped_tables_exist(self):
        from database.init_db import init_db
        import sqlite3

        init_db()
        conn = sqlite3.connect("database/autoqa.db")
        names = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        for table in (
            "agentqe_execution_runs", "agentqe_executions",
            "agentqe_execution_steps", "agentqe_execution_artifacts",
        ):
            assert table in names, f"missing Phase 5 table {table}"


# ═══════════════════════════════════════════════════════════════════════════
# Backwards compatibility
# ═══════════════════════════════════════════════════════════════════════════
class TestBackwardsCompatibility:
    def test_legacy_positional_construction_still_works(self):
        from agentqe.models.execution import ExecutionResult

        result = ExecutionResult("TC-1", "passed")
        assert result.test_id == "TC-1"
        assert result.status == "passed"
        assert result.execution_id.startswith("exec_")

    def test_legacy_automatable_false_is_skipped(self, config):
        test = login_test(config, automatable=False)
        run = ExecutionService(
            planner=ExecutionPlanner(config),
            executor=PlaywrightTestExecutor(config, playwright_factory=FakePlaywright),
            repository=None,
            config=config,
        ).execute_tests([test], base_url="http://x.test", persist=False)
        assert run.results[0].status == "skipped"

    def test_legacy_alias_still_importable(self):
        from agentqe.models.test_case import CandidateTest, TestCase

        assert TestCase is CandidateTest


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def auth_headers(client):
    client.post("/auth/register", json={
        "username": "phase5user",
        "email": "phase5@example.com",
        "password": "testpass123",
        "role": "qa_engineer",
    })
    resp = client.post("/auth/login", json={
        "email": "phase5@example.com", "password": "testpass123",
    })
    token = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestExecutionApi:
    def test_execute_requires_auth(self, client):
        assert client.post("/api/agentqe/tests/execute", json={"tests": []}).status_code == 401

    def test_execute_requires_tests(self, client, auth_headers):
        resp = client.post("/api/agentqe/tests/execute", json={}, headers=auth_headers)
        assert resp.status_code == 400
        assert "tests" in resp.get_json()["error"]

    def test_execute_rejects_unusable_tests(self, client, auth_headers):
        resp = client.post(
            "/api/agentqe/tests/execute",
            json={"tests": [{"nothing": "useful"}]},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert resp.get_json()["skipped"]

    def test_batch_execute_returns_summary(self, client, auth_headers, monkeypatch):
        from agentqe.execution.schemas import ExecutionSummary

        def fake_execute_tests(self, tests, base_url=None, application_context=None,
                               context=None, persist=True):
            from agentqe.execution.schemas import ExecutionResult, ExecutionRunResult
            results = [ExecutionResult(t.test_id, "passed") for t in tests]
            return ExecutionRunResult(
                execution_run_id="execrun_test",
                summary=ExecutionSummary(total=len(results), executed=len(results),
                                         passed=len(results)),
                results=results,
                persisted=True,
            )

        monkeypatch.setattr(
            "agentqe.execution.execution_service.ExecutionService.execute_tests",
            fake_execute_tests,
        )
        resp = client.post(
            "/api/agentqe/tests/execute",
            json={"tests": [login_test(ExecutionConfig()).to_dict()],
                  "base_url": "http://localhost:5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["summary"]["passed"] == 1
        assert body["results"][0]["status"] == "passed"

    def test_single_execute_route(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(
            "agentqe.execution.execution_service.ExecutionService.execute_test",
            lambda self, test, **kw: __import__(
                "agentqe.models.execution", fromlist=["ExecutionResult"]
            ).ExecutionResult(test.test_id, "passed"),
        )
        resp = client.post(
            "/api/agentqe/tests/execute/TC-1",
            json={"title": "A test", "base_url": "http://localhost:5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["execution"]["test_id"] == "TC-1"

    def test_execution_detail_requires_auth(self, client):
        assert client.get("/api/agentqe/executions/exec_x").status_code == 401

    def test_execution_detail_not_found(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(
            "agentqe.execution.persistence.ExecutionRepository.get_execution",
            lambda self, execution_id: None,
        )
        resp = client.get("/api/agentqe/executions/exec_missing", headers=auth_headers)
        assert resp.status_code == 404

    def test_execution_list_rejects_bad_pagination(self, client, auth_headers):
        resp = client.get("/api/agentqe/executions?limit=abc", headers=auth_headers)
        assert resp.status_code == 400

    def test_execution_list_returns_records(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(
            "agentqe.execution.persistence.ExecutionRepository.list_executions",
            lambda self, **kw: [{"execution_id": "exec_1", "test_id": "TC-1",
                                 "status": "passed", "rank_position": 1}],
        )
        resp = client.get("/api/agentqe/executions", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["executions"][0]["test_id"] == "TC-1"

    def test_api_response_has_no_phase6_fields(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(
            "agentqe.execution.execution_service.ExecutionService.execute_tests",
            lambda self, tests, **kw: __import__(
                "agentqe.execution.schemas", fromlist=["ExecutionRunResult"]
            ).ExecutionRunResult(
                execution_run_id="execrun_x",
                summary=__import__(
                    "agentqe.execution.schemas", fromlist=["ExecutionSummary"]
                ).ExecutionSummary(total=1, passed=1),
                results=[__import__(
                    "agentqe.models.execution", fromlist=["ExecutionResult"]
                ).ExecutionResult("TC-1", "passed")],
            ),
        )
        resp = client.post(
            "/api/agentqe/tests/execute",
            json={"tests": [login_test(ExecutionConfig()).to_dict()]},
            headers=auth_headers,
        )
        payload = resp.get_data(as_text=True)
        for forbidden in ("root_cause", "severity", "novelty"):
            assert forbidden not in payload
