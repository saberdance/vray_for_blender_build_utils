#
# V-Ray/Blender Build System
#
# http://vray.cgdo.ru
#
# Author: Andrey M. Izrantsev (aka bdancer)
# E-Mail: izrantsev@cgdo.ru
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
import sys
import glob
import shutil
import inspect
import platform
import subprocess

from .builder import utils
from .builder import Builder

BOOST_VERSION="1.61.0"


def getDepsCompilationData(self, prefix, wd, jobs):
	def dbg(x):
		sys.stdout.write('%s\n' % x)
		sys.stdout.flush()
		return True

	def getChDirCmd(newDir):
		return lambda: os.chdir(newDir) or True

	def getDownloadCmd(url, name):
		return lambda: dbg('wget -c %s -O %s/%s' % (url, wd, name)) and 0 == os.system('wget -c "%s" -O %s/%s' % (url, wd, name))

	def removeSoFile(path):
		if os.path.isfile(path):
			dbg('Removing so file [%s]' % path)
			os.remove(path)
			return True
		return False

	def getRemoveSoFiles(dir):
		return lambda: all([removeSoFile(path) for path in glob.glob('%s/*.dylib*')])

	steps = (
		('boost', '%s/boost-%s' % (prefix, BOOST_VERSION),(
			getChDirCmd(wd),
			getDownloadCmd("http://sourceforge.net/projects/boost/files/boost/%s/boost_%s.tar.bz2/download" % (BOOST_VERSION, BOOST_VERSION.replace('.', '_')), 'boost.tar.bz2'),
			'tar -xf boost.tar.bz2',
			'mv boost_%s boost-%s' % (BOOST_VERSION.replace('.', '_'), BOOST_VERSION),
			getChDirCmd(os.path.join(wd, 'boost-%s' % BOOST_VERSION)),
			'./bootstrap.sh',
			'./b2 -j %s -a link=static threading=multi --layout=tagged --with-system --with-filesystem --with-thread --with-regex --with-locale --with-date_time --with-wave --prefix=%s/boost-%s --disable-icu boost.locale.icu=off install'
				% (jobs, prefix, BOOST_VERSION),
			'./b2 clean',
			'ln -s %s/boost-%s %s/boost' % (prefix, BOOST_VERSION, prefix),
			getRemoveSoFiles('%s/boost/lib' % prefix)
		)),
	)

	return steps


def DepsBuild(self):
	prefix = '/opt/lib' if utils.get_linux_distribution()['short_name'] == 'centos' else '/opt'

	if self.jenkins and self.dir_blender_libs == '':
		sys.stderr.write('Running on jenkins and dir_blender_libs is missing!\n')
		sys.stderr.flush()
		sys.exit(-1)

	if self.dir_blender_libs != '':
		prefix = self.dir_blender_libs

	wd = os.path.expanduser('~/blender-libs-builds')
	if self.jenkins:
		wd = os.path.join(prefix, 'builds')

	sys.stdout.write('Blender libs build dir [%s]\n' % wd)
	sys.stdout.write('Blender libs install dir [%s]\n' % prefix)
	sys.stdout.flush()

	if not os.path.isdir(wd):
		os.makedirs(wd)

	self._blender_libs_location = prefix

	data = getDepsCompilationData(self, prefix, wd, self.build_jobs)

	if self.mode_test:
		# TODO: print out commands
		return

	sys.stdout.write('Building dependencies...\n')

	for item in data:
		if os.path.exists(item[1]):
			sys.stdout.write('%s already installed, skipping ...\n' % item[1])
			continue

		sys.stdout.write('Installing %s...\n' % item[0])
		fail = False
		for step in item[2]:
			sys.stdout.write("CWD %s\n" % os.getcwd())
			sys.stdout.flush()
			if callable(step):
				sys.stdout.write('Callable step: \n\t%s\n' % inspect.getsource(step).strip())
				sys.stdout.flush()
				if not step():
					fail = True
					break
				sys.stdout.write('\n')
			else:
				sys.stdout.write('Command step: \n\t%s\n' % step)
				sys.stdout.flush()
				res = subprocess.call(step, shell=True)
				sys.stderr.flush()
				if res != 0:
					fail = True
					break
		if fail:
			sys.stderr.write('Failed! Removing [%s] if it exists and stopping...\n' % item[1])
			sys.stderr.flush()
			if os.path.exists(item[1]):
				utils.remove_directory(item[1])
			sys.exit(-1)


def PatchLibs(self):
	boost_root = os.path.join(self.jenkins_kdrive_path, 'boost', 'boost_1_61_0')

	mac_version_names = {
		"10.9": "mavericks",
		"10.8": "mountain_lion",
		"10.6": "snow_leopard",
	}

	mac_version = '.'.join(platform.mac_ver()[0].split('.')[0:2])
	mac_name = mac_version_names[mac_version] if mac_version in mac_version_names else None
	sys.stdout.write('Mac ver full [%s] -> %s == %s\n' % (str(platform.mac_ver()), mac_version, mac_name))
	sys.stdout.flush()

	boost_lib = os.path.join(boost_root, 'lib', '%s_x64' % mac_name)

	if not mac_name or not os.path.exists(boost_lib):
		sys.stderr.write('Boost path [%s] missing for this version of mac!\n' % boost_lib)
		sys.stderr.flush()

		mac_name = mac_version_names['10.9']
		boost_lib = os.path.join(boost_root, 'lib', '%s_x64' % mac_name)

		if not mac_name or not os.path.exists(boost_lib):
			sys.stderr.write('Boost path [%s] missing for this version of mac... exiting!\n' % boost_lib)
			sys.stderr.flush()
			sys.exit(1)
		else:
			sys.stderr.write('Trying to build with [%s] instead!\n' % boost_lib)
			sys.stderr.flush()

	boost_lib_dir = os.path.join(boost_lib, 'gcc-4.2-cpp')

	python_patch = os.path.join(self.dir_source, 'blender-for-vray-libs', 'Darwin', 'pyport.h')
	patch_steps = [
		"svn --non-interactive --trust-server-cert checkout --force https://svn.blender.org/svnroot/bf-blender/trunk/lib/darwin-9.x.universal lib/darwin-9.x.universal",
		"svn --non-interactive --trust-server-cert checkout --force https://svn.blender.org/svnroot/bf-blender/trunk/lib/darwin lib/darwin",
		"svn --non-interactive --trust-server-cert checkout --force https://svn.blender.org/svnroot/bf-blender/trunk/lib/win64_vc12 lib/win64_vc12",
		"cp -Rf lib/win64_vc12/opensubdiv/include/opensubdiv/* lib/darwin-9.x.universal/opensubdiv/include/opensubdiv/",
		"cp lib/darwin-9.x.universal/png/lib/libpng12.a lib/darwin-9.x.universal/png/lib/libpng.a",
		"cp lib/darwin-9.x.universal/png/lib/libpng12.la lib/darwin-9.x.universal/png/lib/libpng.la",
		"cp -f %s lib/darwin-9.x.universal/python/include/python3.5m/pyport.h" % python_patch,
		"cp -f %s lib/darwin/python/include/python3.5m/pyport.h" % python_patch,
	]

	# if self.teamcity_project_type == 'vb35':
	# 	# for vb35 get boost from sdk/mac
	# 	patch_steps = patch_steps + [
	# 		"mkdir -p lib/darwin-9.x.universal/release/site-packages",
	# 		"rm -rf lib/darwin-9.x.universal/boost_1_60",
	# 		"mv lib/darwin-9.x.universal/boost lib/darwin-9.x.universal/boost_1_60",
	# 		"mkdir -p lib/darwin-9.x.universal/boost/include",
	# 		"cp -r %s/boost lib/darwin-9.x.universal/boost/include/boost" % boost_root,
	# 		"cp -r %s lib/darwin-9.x.universal/boost/lib" % boost_lib_dir,
	# 	]
	# else:
	# 	pass
	# 	# for vb30 get boost from prebuilt libs
	# 	patch_steps = patch_steps + [
	# 		"cp -r %s lib/darwin-9.x.universal/boost" % os.path.join(self.dir_blender_libs, 'boost-%s' % BOOST_VERSION),
	# 	]

	os.chdir(os.path.join(self.dir_source, 'lib', 'darwin-9.x.universal'))
	os.system('svn revert -R .')
	os.chdir(self.dir_source)

	for step in patch_steps:
		sys.stdout.write('MAC patch step [%s]\n' % step)
		sys.stdout.flush()
		os.system(step)

	sys.stdout.flush()


class MacBuilder(Builder):
	def config(self):
		# Not used on OS X anymore
		pass

	def post_init(self):
		if utils.get_host_os() == utils.MAC:
			DepsBuild(self)
			PatchLibs(self)

	def compile(self):
		cmake_build_dir = os.path.join(self.dir_build, "blender-cmake-build")
		if self.build_clean and os.path.exists(cmake_build_dir):
			utils.remove_directory(cmake_build_dir)
		if not os.path.exists(cmake_build_dir):
			os.makedirs(cmake_build_dir)

		cmake = ['cmake']

		cmake.append("-G")
		cmake.append("Ninja")

		cmake.append("-DCMAKE_BUILD_TYPE=Release")
		cmake.append('-DCMAKE_INSTALL_PREFIX=%s' % self.dir_install_path)
		cmake.append("-DWITH_VRAY_FOR_BLENDER=ON")
		cmake.append("-DWITH_MANUAL_BUILDINFO=%s" % utils.GetCmakeOnOff(self.teamcity))
		cmake.append("-DPNG_LIBRARIES=png12")
		cmake.append("-DWITH_ALEMBIC=ON")

		if self.teamcity_project_type == 'vb35':
			cmake.append("-DUSE_BLENDER_VRAY_ZMQ=ON")
			cmake.append("-DLIBS_ROOT=%s" % utils.path_join(self.dir_source, 'blender-for-vray-libs'))
			cmake.append("-DWITH_CXX11=ON")
			# cmake.append("-DLIBDIR=%s" % utils.path_join(self.dir_source, 'lib', 'darwin-9.x.universal'))
			cmake.append("-DWITH_GAMEENGINE=OFF")
			cmake.append("-DWITH_PLAYER=OFF")
			cmake.append("-DWITH_LIBMV=OFF")
			cmake.append("-DWITH_OPENCOLLADA=OFF")
			cmake.append("-DWITH_CYCLES=ON")
			cmake.append("-DWITH_MOD_OCEANSIM=OFF")
			cmake.append("-DWITH_OPENCOLORIO=ON")
			cmake.append("-DWITH_OPENIMAGEIO=ON")
			cmake.append("-DWITH_IMAGE_OPENEXR=OFF")
			cmake.append("-DWITH_IMAGE_OPENJPEG=OFF")
			cmake.append("-DWITH_FFTW3=OFF")
			cmake.append("-DWITH_CODEC_FFMPEG=OFF")
			cmake.append("-DCMAKE_OSX_DEPLOYMENT_TARGET=")
		else:
			cmake.append("-DWITH_GAMEENGINE=%s" % utils.GetCmakeOnOff(self.with_ge))
			cmake.append("-DWITH_PLAYER=%s" % utils.GetCmakeOnOff(self.with_player))
			cmake.append("-DWITH_LIBMV=%s" % utils.GetCmakeOnOff(self.with_tracker))
			cmake.append("-DWITH_OPENCOLLADA=%s" % utils.GetCmakeOnOff(self.with_collada))
			cmake.append("-DWITH_CYCLES=%s" % utils.GetCmakeOnOff(self.with_cycles))
			cmake.append("-DWITH_MOD_OCEANSIM=ON")
			# TODO: cmake.append("-DWITH_OPENSUBDIV=ON")
			cmake.append("-DWITH_FFTW3=ON")



		cmake.append(self.dir_blender)

		sys.stdout.write('cmake args:\n%s\n' % '\n\t'.join(cmake))
		sys.stdout.flush()

		os.chdir(cmake_build_dir)
		res = subprocess.call(cmake)
		if not res == 0:
			sys.stderr.write("There was an error during configuration!\n")
			sys.exit(1)

		self.write_buildinfo(cmake_build_dir)

		make = ['ninja']
		make.append('-j%s' % self.build_jobs)
		make.append('install')

		res = subprocess.call(make)
		if not res == 0:
			sys.stderr.write("There was an error during the compilation!\n")
			sys.exit(1)

	def package(self):
		subdir = "macos" + "/" + self.build_arch

		release_path = utils.path_join(self.dir_release, subdir)

		if not self.mode_test:
			utils.path_create(release_path)

		# Example: vrayblender-2.60-42181-macos-10.6-x86_64.tar.bz2
		installer_name = utils.GetPackageName(self, ext='dmg')
		archive_name = utils.GetPackageName(self, ext='zip')
		bin_name = utils.GetPackageName(self, ext='bin')
		archive_path = utils.path_join(release_path, installer_name)

		utils.GenCGRInstaller(self, archive_path, InstallerDir=self.dir_cgr_installer)

		sys.stdout.write("Generating archive: %s\n" % archive_name)
		sys.stdout.write("  in: %s\n" % (release_path))

		cmd = "zip %s %s" % (archive_name, installer_name)

		sys.stdout.write("Calling: %s\n" % (cmd))
		sys.stdout.write("  in: %s\n" % (self.dir_install))

		if not self.mode_test:
			os.chdir(release_path)
			os.system(cmd)

		artefacts = (
			os.path.join(release_path, installer_name),
			os.path.join(release_path, bin_name),
			os.path.join(release_path, archive_name),
		)

		sys.stdout.write("##teamcity[setParameter name='env.ENV_ARTEFACT_FILES' value='%s']" % '|n'.join(artefacts))
		sys.stdout.flush()

		return subdir, archive_path.replace('.dmg', '.zip')
