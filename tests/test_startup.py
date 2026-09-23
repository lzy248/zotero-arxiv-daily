"""Keep the BM25 entry point free of eager model initialization."""
import subprocess
import sys


def test_executor_import_does_not_load_model_libraries():
    result = subprocess.run([sys.executable, '-c', '''
import sys
import zotero_arxiv_daily.executor
prefixes = ('torch', 'sentence_transformers', 'transformers', 'peft', 'pymupdf', 'pymupdf4llm', 'onnxruntime')
assert not any(name == p or name.startswith(p + '.') for name in sys.modules for p in prefixes)
'''], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
