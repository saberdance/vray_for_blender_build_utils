#
# V-Ray For Blender jenkins Build Wrapper
#
# http://chaosgroup.com
#
# Author: Andrei Izrantcev
# E-Mail: andrei.izrantcev@chaosgroup.com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# All Rights Reserved. V-Ray(R) is a registered trademark of Chaos Software.
#

import os
import re
import sys
import glob
import time
import platform
import subprocess

from builder import utils

def setup_msvc_2013(cgrepo):
    env = {
        'INCLUDE' : [
            "{CGR_SDK}/msvs2013/PlatformSDK/Include/shared",
            "{CGR_SDK}/msvs2013/PlatformSDK/Include/um",
            "{CGR_SDK}/msvs2013/PlatformSDK/Include/winrt",
            "{CGR_SDK}/msvs2013/PlatformSDK/Include/ucrt",
            "{CGR_SDK}/msvs2013/include",
            "{CGR_SDK}/msvs2013/atlmfc/include",
        ],

        'LIB' : [
            "{CGR_SDK}/msvs2013/PlatformSDK/Lib/winv6.3/um/x64",
            "{CGR_SDK}/msvs2013/PlatformSDK/Lib/ucrt/x64",
            "{CGR_SDK}/msvs2013/atlmfc/lib/amd64",
            "{CGR_SDK}/msvs2013/lib/amd64",
        ],

        'PATH' : [
                "{CGR_SDK}/msvs2013/bin/amd64",
                "{CGR_SDK}/msvs2013/bin",
                "{CGR_SDK}/msvs2013/PlatformSDK/bin/x64",
            ] + os.environ['PATH'].split(os.pathsep)
        ,
    }
    os.environ['__MS_VC_INSTALL_PATH'] = "{CGR_SDK}/msvs2013"
    for var in env:
        os.environ[var] = ";".join(env[var]).format(CGR_SDK=cgrepo)


def main(args):
    sys.stdout.write('jenkins args:\n%s\n' % str(args))
    sys.stdout.flush()

    blender_branch = args.jenkins_blender_git_ref
    sys.stdout.write('Blender git ref:\t %s\n' % blender_branch)
    sys.stdout.flush()

    # minimal build is only true if build_mode == 'default'
    minimal_build = False
    if args.jenkins_build_mode == 'default':
        minimal_build = args.jenkins_minimal_build  in ['1', 'yes', 'true']
        args.jenkins_build_mode = 'nightly'
        sys.stdout.write('\n\tjenkins_build_mode is set to "default", building "nightly" version and *not* uploading\n')
        sys.stdout.flush()

    dir_build = os.getcwd()
    os.environ['http_proxy'] = 'http://10.0.0.1:1234/'
    os.environ['https_proxy'] = 'https://10.0.0.1:1234/'
    os.environ['ftp_proxy'] = '10.0.0.1:1234'
    os.environ['socks_proxy'] = '10.0.0.1:1080'

    cgrepo = os.environ['VRAY_CGREPO_PATH']
    kdrive_os_dir_name = {
        utils.WIN: 'win',
        utils.LNX: 'linux',
        utils.MAC: 'mac',
    }[utils.get_host_os()]
    kdrive = os.path.join(cgrepo, 'sdk', kdrive_os_dir_name)

    if sys.platform == 'win32':
        setup_msvc_2013(kdrive)

    dir_source = os.path.join(args.jenkins_perm_path, 'blender-dependencies')
    if not os.path.exists(dir_source):
        os.makedirs(dir_source)
    else:
        # if job is interrupted while in git operation this file is left behind
        lock_file = os.path.join(dir_source, 'vrayserverzmq','.git','modules','extern','vray-zmq-wrapper','modules','extern','cppzmq','index.lock')
        if os.path.exists(lock_file):
            utils.remove_path(lock_file)

    ### ADD NINJA TO PATH
    ninja_path = 'None'
    if sys.platform == 'win32':
        ninja_path = os.path.join(cgrepo, 'build_scripts', 'cmake', 'tools', 'bin')
    else:
        ninja_path = os.path.join(os.environ['CI_ROOT'], 'ninja', 'ninja')
    sys.stdout.write('Ninja path [%s]\n' % ninja_path)
    sys.stdout.flush()
    os.environ['PATH'] = ninja_path + os.pathsep + os.environ['PATH']

    ### CLONE REPOS
    blender_modules = [
        "release/scripts/addons_contrib",
        "source/tools",
        "release/scripts/addons",
        'intern/vray_for_blender_rt/extern/vray-zmq-wrapper',
        'release/datafiles/locale', # WITH_INTERNATIONAL
    ]

    os.chdir(dir_source)
    utils.remove_directory(os.path.join(dir_source, 'blender'))
    utils.get_repo('git@github.com:ChaosGroup/blender_with_vray_additions',
                   branch=blender_branch,
                   submodules=blender_modules,
                   target_name='blender')

    utils.get_repo('ssh://gitolite@mantis.chaosgroup.com:2047/vray_for_blender_libs',
                   target_name='blender-for-vray-libs')

    utils.get_repo('ssh://gitolite@mantis.chaosgroup.com:2047/vray_for_blender_server.git',
                   branch=args.jenkins_zmq_branch,
                   submodules=['extern/vray-zmq-wrapper'],
                   target_name='vrayserverzmq')

    os.chdir(dir_build)

    ### ADD APPSDK PATH
    bl_libs_os_dir_name = {
        # TODO: fix this for vc14
        utils.WIN: 'Windows',
        utils.LNX: 'Linux',
        utils.MAC: 'Darwin',
    }[utils.get_host_os()]
    appsdk_path = os.path.join(dir_source, 'blender-for-vray-libs', bl_libs_os_dir_name, 'appsdk')
    appsdk_version = '20170307'# re.match(r'.*?vray\d{5}-(\d{8})\.(?:tar\.xz|7z)*?', appsdk_remote_name).groups()[0]
    os.environ['CGR_APPSDK_PATH'] = appsdk_path
    os.environ['CGR_APPSDK_VERSION'] = appsdk_version
    os.environ['CGR_BUILD_TYPE'] = args.jenkins_build_type
    sys.stdout.write('CGR_APPSDK_PATH [%s], CGR_APPSDK_VERSION [%s]\n' % (appsdk_path, appsdk_version))
    sys.stdout.flush()

    python_exe = sys.executable

    sys.stdout.write('jenkins args:\n%s\n' % str(args))
    sys.stdout.flush()

    cmd = [python_exe]
    cmd.append("vb25-patch/build.py")
    cmd.append("--jenkins")
    cmd.append('--dir_source=%s' % dir_source)
    cmd.append('--dir_build=%s' % dir_build)

    cmd.append('--github-src-branch=%s' % blender_branch)
    cmd.append('--teamcity_zmq_server_hash=%s' % utils.get_git_head_hash(os.path.join(dir_source, 'vrayserverzmq')))

    cmd.append('--jenkins_kdrive_path=%s' % kdrive)
    os.environ['jenkins_kdrive_path'] = kdrive
    cmd.append('--jenkins_output=%s' % args.jenkins_output)


    dir_blender_libs = os.path.join(dir_source, 'prebuilt-libs')
    if not os.path.exists(dir_blender_libs):
        sys.stdout.write('Missing prebuilt-libs path [%s], trying to create\n' % dir_blender_libs)
        sys.stdout.flush()
        os.makedirs(dir_blender_libs)
    cmd.append('--dir_blender_libs=%s' % dir_blender_libs)

    if args.jenkins_exporter_git_ref != 'master':
        cmd.append('--github-exp-branch=%s' % args.jenkins_exporter_git_ref)

    cmd.append('--build_clean')
    cmd.append('--with_ge')
    cmd.append('--with_player')
    cmd.append('--with_collada')
    cmd.append('--with_cycles')
    cmd.append('--with_tracker')
    if utils.get_host_os() == utils.WIN:
        cmd.append('--vc_2013')

    if minimal_build:
        cmd.append('--jenkins_minimal_build')
    cmd.append('--build_mode=%s' % args.jenkins_build_mode)
    cmd.append('--build_type=%s' % args.jenkins_build_type)
    cmd.append('--use_package')
    cmd.append('--use_installer=CGR')
    cmd.append('--dir_cgr_installer=%s' % os.path.join(dir_source, 'blender-for-vray-libs', 'cgr_installer'))

    if args.jenkins_with_static_libc:
        cmd.append('--teamcity_with_static_libc')

    cmd.append('--dev_static_libs')

    cmd.append('--upblender=off')
    cmd.append('--uppatch=off')

    cmd.append('--gcc=gcc')
    cmd.append('--gxx=g++')

    cmd.append('--dir_install=%s' % os.path.join(args.jenkins_output, 'install', 'vray_for_blender'))
    cmd.append('--dir_release=%s' % os.path.join(args.jenkins_output, 'release', 'vray_for_blender'))

    sys.stdout.write('Calling builder:\n%s\n' % '\n\t'.join(cmd))
    sys.stdout.flush()

    return subprocess.call(cmd, cwd=dir_build)


if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(usage="python3 jenkins.py [options]")

    parser.add_argument('--jenkins_output',
        default = "",
        required=True,
    )

    parser.add_argument('--jenkins_perm_path',
        default = "",
        required=True,
    )

    parser.add_argument('--jenkins_blender_git_ref',
        default = "dev/vray_for_blender/vb35",
        required=False,
    )

    parser.add_argument('--jenkins_exporter_git_ref',
        default = "master",
        required=False,
    )

    parser.add_argument('--jenkins_with_static_libc',
        action = 'store_true',
    )

    parser.add_argument('--jenkins_build_mode',
        choices=['nightly', 'release', 'default'],
        default='default',
    )

    parser.add_argument('--jenkins_zmq_branch',
        default='master'
    )

    parser.add_argument('--jenkins_minimal_build',
        default='0',
        choices=['yes', 'no', '1', '0', 'true', 'false'],
        required=False,
    )

    parser.add_argument('--jenkins_build_type',
        choices=['debug', 'release'],
        default = 'release',
        required=True,
    )

    args = parser.parse_args()

    sys.exit(main(args))
