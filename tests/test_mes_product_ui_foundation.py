from mes_api_support import client


def test_control_room_has_product_navigation_groups():
    html = client.get("/mes").text

    assert 'data-nav-section="operate"' in html
    assert 'data-nav-section="trace"' in html
    assert 'data-nav-section="ai-development"' in html
    assert 'data-nav-section="system-audit"' in html
    assert 'href="#assignment-trace"' in html
    assert 'href="#ai-dev"' in html


def test_control_room_exposes_product_page_shells():
    html = client.get("/mes").text

    assert 'class="page-shell operate-shell"' in html
    assert 'class="page-shell trace-shell"' in html
    assert 'class="page-shell ai-dev-shell"' in html
    assert 'data-page-purpose="live-state"' in html
    assert 'data-page-purpose="assignment-evidence"' in html
    assert 'data-page-purpose="policy-debug"' in html


def test_control_room_css_defines_commercial_ui_primitives():
    html = client.get("/mes").text

    assert "--surface-strong" in html
    assert "--focus-ring" in html
    assert ".page-shell" in html
    assert ".section-kicker" in html
    assert ".inspector-grid" in html
    assert ".table-scroll" in html
    assert ".truncate-id" in html
    assert ".raw-json-collapsed" in html


def test_ai_dev_and_assignment_trace_use_inspector_primitives():
    html = client.get("/mes").text

    assert 'id="ai-dev-console"' in html
    assert 'id="assignment-trace-page"' in html
    assert 'class="inspector-grid trace-inspector-grid"' in html
    assert 'class="inspector-grid ai-dev-inspector-grid"' in html
    assert 'id="trace-raw-payload-toggle"' in html
