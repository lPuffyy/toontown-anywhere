"""Makes the Panda3D extension modules importable on iOS.

iOS only loads code that is signed, and the signing tools sign Mach-O files in <App>.app/Frameworks (as .dylib),
not loose .so files next to the Python sources. So the modules live in Frameworks as pymod_<name>.dylib and this
meta-path finder maps `panda3d.<name>` to them.
"""
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys

_MODULES = ("core", "direct", "physics", "fx", "interrogatedb", "ode", "egg", "vision", "skel", "ai", "bullet")


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, frameworks):
        self.frameworks = frameworks

    def find_spec(self, name, path=None, target=None):
        # stdlib extension modules, moved to Frameworks as ext_<name>.dylib so that they get signed
        if "." not in name:
            lib = os.path.join(self.frameworks, "ext_%s.dylib" % name)
            if os.path.exists(lib):
                loader = importlib.machinery.ExtensionFileLoader(name, lib)
                return importlib.util.spec_from_file_location(name, lib, loader=loader)
            return None
        if not name.startswith("panda3d."):
            return None
        short = name.split(".", 1)[1]
        if short not in _MODULES:
            return None
        lib = os.path.join(self.frameworks, "pymod_%s.dylib" % short)
        if not os.path.exists(lib):
            return None
        loader = importlib.machinery.ExtensionFileLoader(name, lib)
        return importlib.util.spec_from_file_location(name, lib, loader=loader)


def install(frameworks):
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder(frameworks))


# --- panda3d.ode: the physics engine is not built for iOS yet (golf and a few minigames use it) ---
_ODE_NAMES = ("OdeBoxGeom", "OdePlaneGeom", "OdeBody", "OdeMass", "OdeTriMeshGeom", "OdeTriMeshData", "OdeRayGeom",
              "OdeUtil", "OdeSphereGeom", "OdeWorld", "OdeSimpleSpace", "OdeJointGroup", "OdeSliderJoint", "OdeHingeJoint",
              "OdeContact", "OdeContactGeom", "OdeSurfaceParameters", "OdeGeom", "OdeSpace", "OdeJoint", "OdeCylinderGeom",
              "OdeCappedCylinderGeom", "OdeHashSpace", "OdeQuadTreeSpace", "OdeContactJoint", "OdeBallJoint", "OdeFixedJoint",
              "OdeUniversalJoint", "OdeAMotorJoint", "OdeLMotorJoint", "OdePlane2dJoint", "OdeNullJoint", "OdeCollisionEntry",
              "OdeTriMeshGeom", "OdeSpace")


class _OdeMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _OdeDummy()


class _OdeDummy(metaclass=_OdeMeta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _OdeDummy()

    def __call__(self, *a, **k):
        return _OdeDummy()

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False


class _OdeStubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        import types
        m = types.ModuleType(spec.name)
        for n in _ODE_NAMES:
            setattr(m, n, _OdeMeta(n, (_OdeDummy,), {}))
        m.__all__ = list(_ODE_NAMES)
        return m

    def exec_module(self, module):
        pass


_orig_find_spec = _Finder.find_spec


def _find_spec_with_ode(self, name, path=None, target=None):
    spec = _orig_find_spec(self, name, path, target)
    if spec is None and name == "panda3d.ode":
        return importlib.machinery.ModuleSpec(name, _OdeStubLoader())
    return spec


_Finder.find_spec = _find_spec_with_ode
