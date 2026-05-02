def test_list_table_output(sample_manifest, capsys):
    from oss_doc_search.list import list_libraries

    list_libraries(sample_manifest, json_output=False)
    captured = capsys.readouterr()
    assert "/vercel/next.js" in captured.out
    assert "945" in captured.out


def test_list_json_output(sample_manifest, capsys):
    from oss_doc_search.list import list_libraries

    list_libraries(sample_manifest, json_output=True)
    captured = capsys.readouterr()
    import json

    data = json.loads(captured.out)
    assert "libraries" in data
    assert len(data["libraries"]) == 3
    assert data["libraries"][0]["id"] == "/vercel/next.js"
