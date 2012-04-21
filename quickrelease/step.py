# ex:ts=4:sw=4:sts=4:et
# -*- tab-width: 4; c-basic-offset: 4; indent-tabs-mode: nil -*-

r"""
The base class for QuickRelease steps, along with error reporting classes, 
custom subclasses of steps, and classes to run the individual parts of the 
steps.

L{Step}s are usually searched for in the C{quickrelease/steps} directory. This behavior can be modified by setting the B{C{QUICKRELEASE_DEFINITIONS_PATH}} to the name of a directory containing both a "processes" and "steps" directory.

If you want to exclude the inclusion of any L{Process}es or L{Step<quickrelease.step.Step>}s in the standard QuickRelease directories, set B{C{QUICKRELEASE_OVERRIDE_DEFAULT_DEFINITIONS}} in the environment.
"""

import os

from quickrelease.exception import ReleaseFrameworkError, ReleaseFrameworkErrorCollection
from quickrelease.utils import GetActivePartners, PrintReleaseFrameworkError

class StepError(ReleaseFrameworkError):
    """
    An exception subclassed from L{ReleaseFrameworkError<quickrelease.exception.ReleaseFrameworkError>} which provides a more useful error message about the specific L{Step} the error occured in.
    """
    def __init__(self, stepObj, errStr, *args, **kwargs):
        ReleaseFrameworkError.__init__(self, errStr)

        assert isinstance(stepObj, Step), 'StepErrors require a Step object'
        self.erroredStep = stepObj

        self._partnerStr = ""
        if isinstance(stepObj, PartnerStep):
            self._partnerStr = " (partner: %s)" % (
             stepObj.GetActivePartner())

    def __str__(self):
        return "Error in step %s%s: %s" % (str(self.erroredStep),
         self._partnerStr, ReleaseFrameworkError.__str__(self))

class StandardStepRunner(object):
    def __init__(self, *args, **kwargs):
        object.__init__(self)

    def DoPreflight(self, stepObj):
        stepObj.Preflight()

    def DoExecute(self, stepObj):
        stepObj.Execute()

    def DoVerify(self, stepObj):
        stepObj.Verify()

    def DoNotify(self, stepObj):
        stepObj.Notify()

class Step(object):
    def __init__(self, *args, **kwargs):
        """
        Construct a L{Step} object.

        @param process: The parent-process this L{Step} belongs to.
        @type process: L{Process<quickrelease.process.Process>}

        @param runner: The L{Step}-runner to use for this L{Step}. This allows different types of L{Step}'s to modify the logic of what it means to "run" a step if they so choose (e.g. a L{PartnerStep}).
        @type runner: object
        """
        object.__init__(self)
        self._parentProcess = None
        self._runner = StandardStepRunner()

        if kwargs.has_key('process'):
            self._parentProcess =  kwargs['process']

        if kwargs.has_key('runner'):
            self._runner = kwargs['runner']

    def __str__(self):
        """The L{Step}'s name."""
        return self.__class__.__name__ 

    def _GetRunner(self): return self._runner
    def _GetParentProcess(self): return self._parentProcess
    def _GetConfig(self):
        if self.process is None:
            return None
        return self.process.config

    runner = property(_GetRunner)
    """Return the runner object responsible for running the parts of the step. Read-only.
    @type: Runner object"""

    config = property(_GetConfig)
    """The config associated with the L{Step}'s parent process, if any. Read-only.
    @type: L{ConfigSpec<quickrelease.config.ConfigSpec>}"""

    process = property(_GetParentProcess) 
    """The process this step is a part of, if any. Read-only.
    @type: L{Process<quickrelease.process.Process>}"""

    def Preflight(self):
        """
        A method intended for L{Step}s to override with any activities which 
        must be executed before I{either} the L{Execute<quickrelease.step.Step.Execute>} or L{Verify<quickrelease.step.Step.Verify>} methods need to be executed, if any such activities exist.
        """
        pass

    def Execute(self):
        """
        A method intended for dervied L{Step}s to override with the execution logic of the particular L{Process} step.

        B{Note}: This method B{must} be redefined by the dervied L{Step}.

        @raise NotImplementedError: If the derived L{Step} does not define an C{Execute} method.
        """
        raise NotImplementedError("Need implementation for %s::Execute()" % 
         (str(self)))

    def Verify(self):
        """
        A method intended for dervied L{Step}s to override with the unit test-like verification logic of the particular L{Process} step.

        B{Note}: This method B{must} be redefined by the dervied L{Step}.

        @raise NotImplementedError: If the derived L{Step} does not define an C{Verify} method.
        """
        raise NotImplementedError("Need implementation for %s::Verify()" % 
         (str(self)))
  
    def Notify(self):
        """
        A method intended for L{Step}s to override with any notifications that should occur after a step has successful been executed and/or verified.

        B{Note}: Currently, these notifications will fire even if only the verification-steps are run.
        """
        pass

    # We're kinda cheating here; when using it, it looks like SimpleStepError
    # is an exception type, not a function; it's mostly a convenience function
    # for creating a StepError Exception with a simple message, so we don't
    # have to pass the step object the StepError expects explicitly.
    def SimpleStepError(self, errStr, details=None):
        """
        A convenience method for creating a L{StepError} with a simple message,
        so users don't have to pass the L{Step} object the L{StepError} expects
        explicitly.
        
        @param errStr: the error string
        @type errStr: C{str}

        @param details: Extra details about the error condition.
        @type details: Variable

        @return: An initialized L{StepError} with the current step associated to it.
        @rtype: L{StepError}
        """
        return StepError(self, errStr, details=details)

class PartnerStepRunner(object):
    def __init__(self, *args, **kwargs):
        object.__init__(self)

    def _RunPartnerStepMethod(self, stepObj, methodName):
        conf = stepObj.config
        rootDir = conf.rootDir
        errors = []

        for p in GetActivePartnerList(conf):
            try:
                os.chdir(rootDir)
                stepObj.activePartner = p
                stepMethod = getattr(stepObj, methodName)
                stepMethod()
            except ReleaseFrameworkError, ex:
                if stepObj.haltOnFirstError:
                    raise ex
                else:
                    # Unless we're in quiet mode...
                    PrintReleaseFrameworkError(ex)
                    errors.append(ex)

        if len(errors) != 0:
            raise ReleaseFrameworkErrorCollection(errors)

    def DoPreflight(self, stepObj):
        self._RunPartnerStepMethod(stepObj, "Preflight")

    def DoExecute(self, stepObj):
        self._RunPartnerStepMethod(stepObj, "Execute")

    def DoVerify(self, stepObj):
        self._RunPartnerStepMethod(stepObj, "Verify")

    def DoNotify(self, stepObj):
        self._RunPartnerStepMethod(stepObj, "Notify")

class PartnerStep(Step):
    """
    A special type of L{Step} which will perform the requested C{Execute} and
    C{Verify} methods for all active partners (as determined by L{GetActivePartnerList<quickrelease.utils.GetActivePartnerList>}).

    Subclasses may call the the constructor of C{PartnerStep} with the following
    keywords to modify its behavior:

      1. C{auto_set_partner_config}: By default, when the L{PartnerStep} sets the next partner to execute or verify the portion of the current step, it will also set the section of the associated L{ConfigSpec<quickrelease.config.ConfigSpec>} to the active partner section (via a call to L{SetPartnerSection<quickrelease.config.ConfigSpec.SetActiveParnterConfig>}. Setting this to C{False} will disable that bahavior and make the subclassed L{PartnerStep}s responsible for managing the state of their L{ConfigSpec<quickrelease.config.ConfigSpec>}.
      2. C{halt_on_first_error}: By default, if an error is encountered during the execution or verification portion of a L{PartnerStep}, the error will be reported and noted, but the L{Step} will continue for each active partner. Once each active partner's step has been called, I{then} the L{PartnerStep} will halt. For example, say there exist two partners, "Acme" and "Biffco" and a three-step process, consisting of L{PartnerSteps} named C{WillBeOK}, C{WillFailForAcme}, and C{WillNotRun}. By default, C{WillBeOK} will run for Acme and Biffco; C{WillFailForAcme} will run for Acme and fail, and will then run for Biffco, and succeed. At this point, the L{PartnerStep} will halt with the errors, and the last step will not run. If this is set to C{True}, the L{PartnerStep} would immediately halt when it encountered the Acme-error.
    """
    def __init__(self, *args, **kwargs):
        Step.__init__(self, *args, **kwargs)
        self._runner = PartnerStepRunner()
        self._activePartner = None
        self._partnerData = {}

        self.autoSetPartnerConfig = True
        self.haltOnFirstError = False

        if kwargs.has_key('auto_set_partner_config'):
            self.autoSetPartnerConfig = kwargs['auto_set_partner_config']

        if kwargs.has_key('halt_on_first_error'):
            self.haltOnFirstError = kwargs['halt_on_first_error']

    def _GetActivePartner(self): return self._activePartner

    def _SetActivePartner(self, partner):
        if partner not in GetActivePartnerList(self.config):
            raise self.SimpleStepError("Unknown partner '%s'" % (partner))

        self._activePartner = partner

        if self.autoSetPartnerConfig:
            self.config.SetPartnerSection(partner)

        if partner not in self._partnerData.keys():
            self._partnerData[partner] = {}

    activePartner = property(_GetActivePartner, _SetActivePartner)

    def Save(self, key, data):
        """
        Store partner-specific data that may need to persist across a set of C{Execute}/C{Verify} calls.

        @param key: Key to retrieve the data.
        @type key: C{str}

        @param data: The data to store.
        @type data: Variable
        """
        self._partnerData[self.activePartner][key] = data

    def Load(self, key):
        """
        Retrieve partner-specific data that may need to persist across a set of C{Execute}/C{Verify} calls.

        @param key: Key of data to retrieve
        @type key: C{str}

        @raise KeyError: If the data described by the specified key does not exist.
        """
        return self._partnerData[self.activePartner][key]

