import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "fluidd_k3_compat.py"
SPEC = importlib.util.spec_from_file_location("fluidd_k3_compat_upload_test", MODULE_PATH)
COMPAT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPAT)


class FluiddK3UploadTokenTests(unittest.TestCase):
    def test_patch_bundle_accepts_existing_http_token_patches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            assets = root / "assets"
            assets.mkdir()
            bundle = "".join(
                (
                    COMPAT.NEW_WEBCAM_LIST,
                    COMPAT.NEW_WEBCAM_DELETE,
                    "serverSensorsList(){}",
                    COMPAT.NEW_FILE_DOWNLOAD,
                    COMPAT.K3_FILE_API_ORIGIN_METHOD,
                    COMPAT.K3_ONESHOT_TOKEN_METHOD,
                    "async serverFilesUploadPost(e,t,n,r,i){let o="
                    + COMPAT.K3_UPLOAD_ONESHOT_EXPRESSION
                    + ";return o}",
                )
            )
            (assets / "index.js").write_text(bundle, encoding="utf-8")

            COMPAT.patch_bundle(root)

            patched = (assets / "index.js").read_text(encoding="utf-8")
            self.assertIn(COMPAT.K3_ONESHOT_TOKEN_MARKER, patched)
            self.assertIn(COMPAT.K3_UPLOAD_ONESHOT_MARKER, patched)

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
