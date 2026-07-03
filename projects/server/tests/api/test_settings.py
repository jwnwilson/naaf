from interactors.api.settings import Settings


def test_worker_roles_list_parses_csv():
    assert Settings(worker_roles="lead, backend ,qa").worker_roles_list == ["lead", "backend", "qa"]


def test_worker_roles_list_empty_by_default():
    assert Settings().worker_roles_list == []
