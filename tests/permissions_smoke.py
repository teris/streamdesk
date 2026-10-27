"""Exercise inherited recording ACLs and atomic config group preservation locally.
No root access, system users, services or existing directories are changed.
Run with setfacl/getfacl available in PATH.
"""
import grp
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix='streamdesk-permissions-') as temporary:
        base=Path(temporary);native=base/'native';native.mkdir(mode=0o2770)
        config=base/'config'/'mediamtx.yml';config.parent.mkdir();config.write_text('authMethod: internal\nauthInternalUsers: []\npaths: {}\n')
        clip=base/'fixture.mp4';clip.write_bytes(b'permissions-fixture')
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_NATIVE_ROOT=str(native),
                          MEDIAMTX_CONFIG=str(config),STREAMDESK_DEFAULT_CLIP=str(clip))
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        import app
        from scripts.install import storage_permissions
        user_name=pwd.getpwuid(os.geteuid()).pw_name
        storage_permissions(SimpleNamespace(ui_user=user_name,media_user='nobody',mediamtx_config=config,native_root=native))
        with patch.object(app.threading,'Thread'):
            uid=app.add_user('permissions','Fixture-Permissions-Password-123')
        user=app.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
        directory=app.FEATURES.recording_directory(user,'source1',create=True)
        old=os.umask(0o077)
        try:
            recorded=directory/'fixture.mp4';recorded.write_bytes(b'recording')
        finally:os.umask(old)
        acl=subprocess.check_output(['getfacl','-cp',str(recorded)],text=True)
        assert 'user:nobody:rwx' in acl and 'mask::rw-' in acl,acl
        assert 'other::---' in acl,acl
        # Pick an actual supplementary group to catch replacement files losing
        # the MediaMTX-readable group when the UI runs under another primary GID.
        group=next((gid for gid in os.getgroups() if gid!=os.getgid()),os.getgid())
        os.chown(config,-1,group);app.atomic(config,config.read_text())
        assert config.stat().st_gid==group
        assert recorded.read_bytes()==b'recording'
        print('PASS: recording ACLs survive umask 0077; unprivileged atomic config writes retain the existing media group.')


if __name__=='__main__':main()
