import param
import brimfile as bls

from .logging import logger

class bls_param(param.Parameterized):
    file = param.ClassSelector(class_=bls.File, default=None, allow_None=True, allow_refs=True)
    data = param.ClassSelector(class_=bls.Data, default=None, allow_None=True, allow_refs=True)
    analysis = param.ClassSelector(class_=bls.Data.AnalysisResults, default=None, allow_None=True, allow_refs=True)

    def __init__(self, **params):
        super().__init__(**params)

        # Explicit annotation, because param and type hinting is not working properly
        self.file: bls.File
        self.data: bls.Data
        self.analysis: bls.Data.AnalysisResults
    
    def reset(self):
        logger.debug("Resetting bls_input")
        with param.parameterized.batch_call_watchers(self):
            self.file = None
            self.data = None
            self.analysis = None
    
    def is_loaded(self, require_analysis: bool = True) -> bool:
        """
        Whether a file and its data are loaded.

        A data group can have no analysis results at all: with `require_analysis=False`
        these are not needed for the data to be considered as loaded.
        """
        logger.debug(f"Checking if bls_input is fully loaded: file {self.file is not None}, data {self.data is not None}, analysis {self.analysis is not None}")
        loaded = self.file is not None and self.data is not None
        if require_analysis:
            loaded = loaded and self.analysis is not None
        return loaded