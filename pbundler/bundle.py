from __future__ import print_function
from __future__ import absolute_import

__all__ = ['Bundle']

import os
import sys
import time
import traceback
import subprocess
import pkg_resources

from . import PBundlerException
from .util import PBFile
from .pypath import PyPath
from .cheesefile import Cheesefile, CheesefileLock, Cheese, CHEESEFILE, CHEESEFILE_LOCK
from .sources import CheeseshopSource, FilesystemSource
from .localstore import LocalStore


class Bundle:

    def __init__(self, path):
        self.path = path
        self.current_platform = 'cpython'

        self.cheesefile = Cheesefile(os.path.join(self.path, CHEESEFILE))
        self.cheesefile.parse()
        cheesefile_lock_path = os.path.join(self.path, CHEESEFILE_LOCK)
        if os.path.exists(cheesefile_lock_path):
            self.cheesefile_lock = CheesefileLock(cheesefile_lock_path)
            self.cheesefile_lock.parse()
        else:
            self.cheesefile_lock = None

        self.localstore = LocalStore()

    @classmethod
    def load(cls, path=None):
        """Preferred constructor."""

        if path is None:
            path = PBFile.find_upwards(CHEESEFILE)
            if path is None:
                message = ("Could not find %s in path from here to " +
                           "filesystem root.") % (CHEESEFILE)
                raise PBundlerException(message)

        return cls(path)

    def validate_requirements(self):
        self.calculate_requirements()
        pass

    def _add_new_dep(self, dep):
        cheese = Cheese.from_requirement(dep)
        existing = self.required.get(cheese.key)
        if existing:
            # FIXME: check if we're compatible
            return None
        self.required[cheese.key] = cheese
        return cheese

    def _resolve_deps(self):
        for pkg in self.required.values():
            if pkg.source or pkg.dist:
                # don't touch packages where we already know a source (& version)
                continue

            if pkg.path:
                source = FilesystemSource(pkg.path)
                available_versions = source.available_versions(pkg)
                if len(available_versions) == 0:
                    raise PBundlerException("Package %s is not available in %r" % (pkg.name, pkg.path))
                if len(available_versions) != 1:
                    raise PBundlerException("Package %s has multiple versions in %r" % (pgk.name, pkg.path))

                version = available_versions[0]
                pkg.use_from(version, source)

            else:
                # short-circuit remote resolver if we already have this
                # package in the local store.

                if not self.resolve_changes_allowed:
                    # if this is false, then we weren't completely resolved already
                    assert(pkg.is_exact_version())
                    dist = self.localstore.get(pkg)
                    if dist:
                        #print("Short-circuited version check for", pkg.name)
                        pkg.use_dist(dist)
                        continue

                req = pkg.requirement()
                for source in self.cheesefile.sources:
                    print("Querying", repr(source.url), "for", repr(pkg.name))
                    pkg.name = source.canonical_name(pkg)
                    for version in source.available_versions(pkg):
                        if version in req:
                            pkg.use_from(version, source)
                            break

                if pkg.source is None:
                    raise PBundlerException("Package %s %s is not available on any sources." % (pkg.name, pkg.version_req))

        new_deps = []

        for pkg in self.required.values():
            if pkg.dist:
                # don't touch packages where we already have a (s)dist
                continue

            if pkg.path:
                # FIXME: not really the truth
                dist = pkg.source.get_distribution(pkg.source)
                print("Using %s %s from %s" % (pkg.name, pkg.exact_version, pkg.path))
            else:
                dist = self.localstore.get(pkg)
                if dist:
                    print("Using %s %s" % (pkg.name, pkg.exact_version))
                else:
                    # download and unpack
                    dist = self.localstore.prepare(pkg, pkg.source)

            pkg.use_dist(dist)

            for dep in dist.requires():
                new_deps.append(self._add_new_dep(dep))

        # super ugly:
        new_deps = list(set(new_deps))
        if None in new_deps:
            new_deps.remove(None)
        return new_deps

    def install(self, groups):
        self.required = self.cheesefile.collect(groups, self.current_platform)
        self.resolve_changes_allowed = True
        if self.cheesefile_lock:
            #print(repr(self.required))
            #print(repr(self.cheesefile_lock.cheesefile_data))
            if self.cheesefile_lock.matches_cheesefile(self.cheesefile):
                self.required = self.cheesefile_lock.to_required()
                self.resolve_changes_allowed = False
            else:
                print("Resolving packages...")
            # check if all deps from cheesefile are the same as in lockfile.from_cheesefile
            # check if all deps from lockfile.from_cheesefile are in lockfile.from_source
            #### check if all deps from lockfile.from_source are installed

        # wenn ich ein lockfile habe: self.required  aus lockfile.from_source fillen
        # -> resolve
        # neues dep in cheesefile:
        # -> self.required w.o.
        # -> neues dep resolven
        # dep updaten:
        # -> pkg aus self.required loeschen
        # -> rekursiv requirements entfernen wenn sie nicht anderswertig verwendet werden
        # -> als neues dep resolven
        # komplettes update:
        # -> self.required voellig loeschen
        # dep removed:
        # -> pkg aus self.required loeschen
        # -> rekursiv requirements entfernen wenn sie nicht anderswertig verwendet werden

        # TODO: incremental resolving
        while True:
            new_deps = self._resolve_deps()
            if len(new_deps) == 0:
                # done resolving!
                break

        for pkg in self.required.values():
            if getattr(pkg.dist, 'is_sdist', False) is True:
                dist = self.localstore.install(pkg, pkg.dist)
                pkg.use_dist(dist)  # mark as installed

        self._write_cheesefile_lock()
        print("Your bundle is complete.")

    def _write_cheesefile_lock(self):
        if not self.resolve_changes_allowed:
            # HACK: not really the right var or anything
            return

        # TODO: file format is wrong. at least we must consider groups,
        # and we shouldn't rewrite the entire file (think groups, platforms).
        # TODO: write source to lockfile.
        with file(os.path.join(self.path, CHEESEFILE_LOCK), 'wt') as lockfile:
            indent = ' '*4
            lockfile.write("with Cheesefile():\n")
            for pkg in self.cheesefile.collect(['default'], self.current_platform).itervalues():
                lockfile.write(indent+"pkg(%r, %r, path=%r)\n" % (pkg.name, pkg.orig_version_req, pkg.path))
            lockfile.write(indent+"pass\n")
            lockfile.write("\n")

            for source in self.cheesefile.sources:
                #print(source)
                lockfile.write("with from_source(%r):\n" % (source.url))
                for name, pkg in self.required.items():
                    # ignore ourselves and our dependencies (which should
                    # only ever be distribute).
                    if name in ['pbundler','distribute']:
                        continue
                    #print(name, pkg, pkg.source)
                    if pkg.source.url != source.url:
                        continue
                    lockfile.write(indent+"with resolved_pkg(%r, %r):\n" % (pkg.name, pkg.exact_version))
                    for dep in pkg.requirements:
                        name = source.canonical_name(dep)
                        lockfile.write(indent+indent+"pkg(%r, %r)\n" % (name, dep.version_req))
                    lockfile.write(indent+indent+"pass\n")
                lockfile.write(indent+"pass\n")

    def _check_sys_modules_is_clean(self):
        # TODO: Possibly remove this when resolver/activation development is done.
        unclean = []
        for name, module in sys.modules.iteritems():
            source = getattr(module, '__file__', None)
            if source is None or name == '__main__':
                continue
            in_path = False
            for path in sys.path:
                if source.startswith(path):
                    in_path = True
                    break
            if in_path:
                continue
            unclean.append('%s from %s' % (name, source))
        if len(unclean) > 0:
            raise PBundlerException("sys.modules contains foreign modules: %s" % ','.join(unclean))

    def load_cheese(self):
        if getattr(self, 'required', None) is None:
            self.install(['default'])
            #raise PBundlerException("Your bundle is not installed.")

    def enable(self, groups):
        # TODO: remove groups from method sig
        self.load_cheese()

        # reset import path
        new_path = [sys.path[0]]
        new_path.extend(PyPath.clean_path())
        PyPath.replace_sys_path(new_path)

        enabled_path = []
        for pkg in self.required.values():
            pkg.dist.activate(enabled_path)

        new_path = [sys.path[0]]
        new_path.extend(enabled_path)
        new_path.extend(PyPath.clean_path())
        PyPath.replace_sys_path(new_path)

        self._check_sys_modules_is_clean()

    def exec_enabled(self, command):
        # We don't actually need all the cheese loaded, but it's great to
        # fail fast.
        self.load_cheese()

        import pkg_resources
        dist = pkg_resources.get_distribution('pbundler')
        activation_path = os.path.join(dist.location, 'pbundler', 'activation')
        os.putenv('PYTHONPATH', activation_path)
        os.putenv('PBUNDLER_CHEESEFILE', self.cheesefile.path)
        os.execvp(command[0], command)

    def get_cheese(self, name, default=None):
        self.load_cheese()
        return self.required.get(name.upper(), default)
