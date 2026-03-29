import os
import shutil
import tempfile
from git import Repo, GitCommandError


class GitConnector:
    def __init__(self, repo_url, branch="main"):
        self.repo_url = repo_url
        self.branch = branch
        self.local_path = None

    def clone_repo(self):
        temp_dir = tempfile.mkdtemp()
        try:
            self._clone_with_fallback(temp_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        self.local_path = temp_dir
        return temp_dir

    def _clone_with_fallback(self, dest: str):
        """
        Try cloning with the requested branch first.
        If the branch doesn't exist (common on Bitbucket repos that use 'master'
        instead of 'main' or vice-versa), retry without specifying a branch so
        Git picks up the remote HEAD.
        """
        clone_kwargs = {
            "depth": 1,
            "env": {
                # Disable interactive credential prompts so failures are
                # raised immediately instead of hanging.
                "GIT_TERMINAL_PROMPT": "0",
                **os.environ,
            },
        }

        try:
            Repo.clone_from(self.repo_url, dest, branch=self.branch, **clone_kwargs)
        except GitCommandError as primary_err:
            err_msg = str(primary_err).lower()
            # Branch not found or repo is empty on that ref — retry without
            # specifying a branch to let git use the remote's default.
            if (
                "remote branch" in err_msg
                or "not found" in err_msg
                or "couldn't find remote ref" in err_msg
            ):
                # Wipe the failed partial clone attempt before retrying.
                for item in os.listdir(dest):
                    item_path = os.path.join(dest, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                Repo.clone_from(self.repo_url, dest, **clone_kwargs)
            else:
                raise

    def get_file_content(self, file_path):
        if not self.local_path:
            self.clone_repo()
        abs_path = os.path.join(self.local_path, file_path)
        # Try UTF-8 first; fall back to latin-1 for files with non-standard encoding.
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(abs_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        # Binary or completely unreadable file — skip it.
        return None

    def cleanup(self):
        if self.local_path and os.path.exists(self.local_path):
            shutil.rmtree(self.local_path, ignore_errors=True)
            self.local_path = None
