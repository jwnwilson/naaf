from adapters.agent.workspace.local import LocalWorkspace


def test_bash_injects_provided_env(tmp_path):
    ws = LocalWorkspace(tmp_path, env={"NAAF_TEST_TOKEN": "secret123"})
    r = ws.bash("echo $NAAF_TEST_TOKEN", timeout_s=10)
    assert r.stdout.strip() == "secret123"


def test_bash_still_inherits_process_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NAAF_AMBIENT", "amb")
    ws = LocalWorkspace(tmp_path)
    r = ws.bash("echo $NAAF_AMBIENT", timeout_s=10)
    assert r.stdout.strip() == "amb"
