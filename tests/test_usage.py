from cli.usage import MISSING_NODE_MESSAGE, build_argv, node_runtime_available


def test_node_runtime_available_true_when_npx_on_path():
    def fake_which(exe):
        return "/usr/bin/npx" if exe == "npx" else None

    assert node_runtime_available(which=fake_which) is True


def test_node_runtime_available_true_when_only_bunx_on_path():
    def fake_which(exe):
        return "/usr/bin/bunx" if exe == "bunx" else None

    assert node_runtime_available(which=fake_which) is True


def test_node_runtime_available_false_when_neither_present():
    assert node_runtime_available(which=lambda exe: None) is False


def test_build_argv_prepends_npx_ccusage():
    argv = build_argv([])
    assert argv == ["npx", "-y", "ccusage@latest"]


def test_build_argv_appends_passthrough_args_unmodified():
    argv = build_argv(["claude", "session", "--json"])
    assert argv == ["npx", "-y", "ccusage@latest", "claude", "session", "--json"]


def test_missing_node_message_mentions_npx_and_ccusage():
    assert "npx" in MISSING_NODE_MESSAGE.lower()
    assert "ccusage" in MISSING_NODE_MESSAGE.lower()
