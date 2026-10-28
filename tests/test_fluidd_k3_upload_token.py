import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fluidd_k3_compat.py"
SPEC = importlib.util.spec_from_file_location("fluidd_k3_compat_upload_test", MODULE_PATH)
COMPAT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPAT)


class FluiddK3UploadTokenTests(unittest.TestCase):
    def test_replaces_missing_websocket_token_rpc_with_http_endpoint(self):
        source = (
            "async serverFilesUploadPost(e,t,n,r,i){let a=new FormData;"
            "a.append(`file`,e,e.name);let o=this.isTrustedUser?null:"
            "await T.accessOneshotToken();return xm.postForm(`/server/files/upload${o?`?token=${o}`:``}`,a,i)}"
        )

        patched, changed = COMPAT.patch_http_upload_oneshot_token(source)

        self.assertTrue(changed)
        self.assertIn(COMPAT.K3_UPLOAD_ONESHOT_MARKER, patched)
        self.assertIn("/access/oneshot_token", patched)
        self.assertIn("credentials:`same-origin`", patched)
        self.assertNotIn("T.accessOneshotToken()", patched)

    def test_upload_token_patch_is_idempotent(self):
        source = (
            "async serverFilesUploadPost(e,t,n,r,i){let o=this.isTrustedUser?null:"
            "await T.accessOneshotToken();return o}"
        )
        patched, changed = COMPAT.patch_http_upload_oneshot_token(source)
        patched_again, changed_again = COMPAT.patch_http_upload_oneshot_token(patched)

        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(patched, patched_again)

    def test_unknown_upload_token_code_is_left_unchanged(self):
        source = "async serverFilesUploadPost(e,t,n,r,i){return null}"

        patched, changed = COMPAT.patch_http_upload_oneshot_token(source)

        self.assertFalse(changed)
        self.assertEqual(source, patched)


if __name__ == "__main__":
    unittest.main()
