from domain.project import derive_project_key


def test_derives_first_four_alnum_uppercased():
    assert derive_project_key("naaf") == "NAAF"
    assert derive_project_key("Acme Web App") == "ACME"
    assert derive_project_key("my-tool") == "MYTO"


def test_strips_non_alphanumerics_before_truncating():
    assert derive_project_key("A.B-C_D_E") == "ABCD"


def test_falls_back_to_proj_when_no_alphanumerics():
    assert derive_project_key("!!!") == "PROJ"
    assert derive_project_key("") == "PROJ"


def test_suffixes_on_collision():
    assert derive_project_key("Acme", {"ACME"}) == "ACME2"
    assert derive_project_key("Acme", {"ACME", "ACME2"}) == "ACME3"
