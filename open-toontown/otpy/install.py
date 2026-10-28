"""Make `from panda3d.otp import ...` and `from panda3d.toontown import ...` resolve to the pure-Python replacements."""
import sys
import types


def install():
    from . import dna, movement, nametag, suit
    otp = types.ModuleType("panda3d.otp")
    tt = types.ModuleType("panda3d.toontown")
    for m, names in ((nametag, ["CF_speech", "CF_thought", "CF_quicktalker", "CF_timeout", "CF_page_button", "CF_quit_button", "CF_reversed", "CF_snd_openchat",
                                "CF_no_quit_button", "CFSpeech", "CFThought", "CFQuicktalker", "CFTimeout", "CFPageButton", "CFQuitButton", "CFReversed",
                                "CFSndOpenchat", "CFNoQuitButton", "ChatBalloon", "ClickablePopup", "MarginManager", "MarginPopup", "Nametag", "Nametag2d",
                                "Nametag3d", "NametagFloat2d", "NametagFloat3d", "NametagGlobals", "NametagGroup", "WhisperPopup"]),
                     (movement, ["CImpulse", "CMover", "CMoverGroup"])):
        for n in names:
            setattr(otp, n, getattr(m, n))
    for n in ("PosHpr", "DNAAnimBuilding", "DNAAnimProp", "DNABattleCell", "DNACornice", "DNAData", "DNADoor", "DNAFlatBuilding", "DNAFlatDoor", "DNAGroup",
              "DNAInteractiveProp", "DNALandmarkBuilding", "DNALoader", "DNANode", "DNAProp", "DNASign", "DNASignBaseline", "DNASignGraphic", "DNASignText",
              "DNAStorage", "DNAStreet", "DNASuitEdge", "DNASuitPath", "DNASuitPoint", "DNAVisGroup", "DNAWall", "DNAWindows", "getDnaPath", "get_dna_path",
              "loadDNAFile", "loadDNAFileAI", "load_DNA_file", "load_DNA_file_AI"):
        setattr(tt, n, getattr(dna, n))
    for n in ("SuitLeg", "SuitLegList"):
        setattr(tt, n, getattr(suit, n))
    for n in ("CPetBrain", "CPetChase", "CPetFlee"):
        setattr(tt, n, getattr(movement, n))
    sys.modules["panda3d.otp"] = otp
    sys.modules["panda3d.toontown"] = tt
    import panda3d
    panda3d.otp = otp
    panda3d.toontown = tt

    # Every animated model (toons, Cogs, doodles, NPCs, and props such as doors, fish and boats) blends between an animation's frames: most
    # of the game's animations are made at 24 frames a second, which looks stepped on a 60 Hz screen without it. The 'interpolate-frames'
    # setting alone does not switch this on for actors, so do it for every actor as each of its parts loads.
    try:
        from direct.actor.Actor import Actor
        if not getattr(Actor, "_ot_frame_blend", False):
            orig_load = Actor.loadModel

            def loadModel(self, *args, **kw):
                ret = orig_load(self, *args, **kw)
                try:
                    self.setBlend(frameBlend=True)
                except Exception:
                    pass
                return ret
            Actor.loadModel = loadModel
            Actor._ot_frame_blend = True
    except Exception:
        pass
