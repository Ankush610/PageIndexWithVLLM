import re

with open('/home/claude/PageIndexWithVLLM-refactored/indexing.py', 'r') as f:
    content = f.read()

# Find the block to replace - from "_orig_utils = _piu..." to "logger.info("get_page_tokens patch restored")"
old = '''        _orig_utils = _piu.get_page_tokens
        # page_index.py does `from .utils import *` so get_page_tokens is bound
        # directly in page_index's own namespace — patching _piu alone has no
        # effect on the name that page_index_main actually calls.  We must also
        # patch the name inside page_index's module dict.
        _orig_pip   = getattr(_pip, "get_page_tokens", None)

        # Log what the vision extraction actually produced so we can debug
        for i, (content, tokens) in enumerate(prebuilt):
            logger.info(
                "VISION PAGE %d — %d tokens — first 300 chars: %r",
                i + 1, tokens, content[:300]
            )

        def _patched(pdf_path_arg, model=None, pdf_parser="PyPDF2"):
            logger.info(
                "get_page_tokens PATCHED CALLED — returning %d pre-built pages", len(prebuilt)
            )
            return prebuilt

        # Patch all three locations so no call-site is missed:
        #   1. pageindex.utils  – future imports / other callers
        #   2. pageindex.page_index – the wildcard-imported binding used by page_index_main
        _piu.get_page_tokens = _patched
        _pip.get_page_tokens = _patched   # ← this is the binding page_index_main resolves

        # Also wrap verify_toc to log its accuracy so we can diagnose failures
        _orig_verify_toc = _pip.verify_toc
        async def _patched_verify_toc(page_list, list_result, start_index=1, N=None, model=None):
            accuracy, incorrect = await _orig_verify_toc(page_list, list_result, start_index=start_index, N=N, model=model)
            logger.info(
                "verify_toc result — accuracy=%.2f, incorrect=%d, total_items=%d",
                accuracy, len(incorrect), len(list_result)
            )
            for item in list_result[:5]:
                logger.info("  TOC item: title=%r physical_index=%r", item.get('title'), item.get('physical_index'))
            if incorrect:
                for item in incorrect[:3]:
                    logger.info("  INCORRECT: title=%r page=%r", item.get('title'), item.get('page_number'))
            return accuracy, incorrect
        _pip.verify_toc = _patched_verify_toc

        _orig_restore = None
            _piu.get_page_tokens = _orig_utils
            if _orig_pip is not None:
                _pip.get_page_tokens = _orig_pip
            else:
                # wildcard import created the name; remove it so the module
                # falls back to re-importing from utils naturally next time
                try:
                    del _pip.get_page_tokens
                except AttributeError:
                    pass
            logger.info("get_page_tokens patch restored")'''

new = '''        # Log what the vision extraction actually produced so we can debug
        for i, (pg_content, tokens) in enumerate(prebuilt):
            logger.info(
                "VISION PAGE %d — %d tokens — first 300 chars: %r",
                i + 1, tokens, pg_content[:300]
            )

        # page_index.py does `from .utils import *` so get_page_tokens is bound
        # directly in page_index's own namespace — must patch that binding too.
        _orig_utils      = _piu.get_page_tokens
        _orig_pip_tokens = getattr(_pip, "get_page_tokens", None)
        _orig_verify_toc = _pip.verify_toc

        def _patched_get_page_tokens(pdf_path_arg, model=None, pdf_parser="PyPDF2"):
            logger.info(
                "get_page_tokens PATCHED CALLED — returning %d pre-built pages", len(prebuilt)
            )
            return prebuilt

        async def _patched_verify_toc(page_list, list_result, start_index=1, N=None, model=None):
            accuracy, incorrect = await _orig_verify_toc(
                page_list, list_result, start_index=start_index, N=N, model=model
            )
            logger.info(
                "verify_toc result — accuracy=%.2f, incorrect=%d, total_items=%d",
                accuracy, len(incorrect), len(list_result)
            )
            for item in list_result[:5]:
                logger.info("  TOC item: title=%r  physical_index=%r", item.get("title"), item.get("physical_index"))
            for item in incorrect[:3]:
                logger.info("  INCORRECT: title=%r  page=%r", item.get("title"), item.get("page_number"))
            return accuracy, incorrect

        _piu.get_page_tokens = _patched_get_page_tokens
        _pip.get_page_tokens = _patched_get_page_tokens
        _pip.verify_toc      = _patched_verify_toc

        def _patch_restore():
            _piu.get_page_tokens = _orig_utils
            if _orig_pip_tokens is not None:
                _pip.get_page_tokens = _orig_pip_tokens
            else:
                try:
                    del _pip.get_page_tokens
                except AttributeError:
                    pass
            _pip.verify_toc = _orig_verify_toc
            logger.info("patches restored")'''

if old in content:
    content = content.replace(old, new)
    with open('/home/claude/PageIndexWithVLLM-refactored/indexing.py', 'w') as f:
        f.write(content)
    print("SUCCESS")
else:
    print("NOT FOUND")
