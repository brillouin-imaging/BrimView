from enum import Enum
import inspect
import re
import param
import numpy as np

from brimfile.data import Data as bls_data

class CurveFitModel:
    @staticmethod
    def lorentzian(nu, b, a, nu0, gamma, IR = None):
        """Model of a simple lorentzian lineshape

        Parameters
        ----------
        nu : array
            The frequency array
        b : float
            The constant offset of the data
        a : float
            The amplitude of the peak
        nu0 : float
            The center position of the function
        gamma : float
            The FWHM linewidth of the function
        IR : array, optional
            The impulse response of the instrument, by default None

        Returns
        -------
        function
            The function associated to the given parameters
        """
        hwhm = gamma/2
        func = b + a*hwhm**2/((nu-nu0)**2+hwhm**2)
        if IR is not None: return np.convolve(func, IR, "same")
        return func
    
    @staticmethod
    def lorentzian_elastic(nu, ae, be, a, nu0, gamma, IR = None):
        """Model of a simple lorentzian lineshape

        Parameters
        ----------
        nu : array
            The frequency array
        ae : float
            The slope of the first order Taylor expansion of the elastic peak at the position of the peak fitted
        be : float
            The constant offset of the data
        a : float
            The amplitude of the peak
        nu0 : float
            The center position of the function
        gamma : float
            The linewidth of the function
        IR : array, optional
            The impulse response of the instrument, by default None

        Returns
        -------
        function
            The function associated to the given parameters
        """
        func =  ae*nu + CurveFitModel.lorentzian(nu, be, a, nu0, gamma)
        if IR is not None: return np.convolve(func, IR, "same")
        return func
    
    @staticmethod
    def DHO(nu, b, a, nu0, gamma, IR = None):
        """Model of a simple lorentzian lineshape

        Parameters
        ----------
        nu : array
            The frequency array
        b : float
            The constant offset of the data
        a : float
            The amplitude of the peak
        nu0 : float
            The center position of the function
        gamma : float
            The linewidth of the function
        IR : array, optional
            The impulse response of the instrument, by default None

        Returns
        -------
        function
            The function associated to the given parameters
        """
        func = b + a * (gamma*nu0)**2/((nu**2-nu0**2)**2+(gamma*nu)**2)
        # This is to only generate one peak and not a doublet
        if np.sign(nu0) == -1: 
            func = func*(nu<=0)
        else: 
            func = func*(nu>=0)
        if IR is not None: return np.convolve(func, IR, "same")
        return func 
    
    @staticmethod
    def DHO_elastic(nu, ae, be, a, nu0, gamma, IR = None):
        """Model of a simple lorentzian lineshape

        Parameters
        ----------
        nu : array
            The frequency array
        ae : float
            The slope of the first order Taylor expansion of the elastic peak at the position of the peak fitted
        be : float
            The constant offset of the data
        a : float
            The amplitude of the peak
        nu0 : float
            The center position of the function
        gamma : float
            The linewidth of the function
        IR : array, optional
            The impulse response of the instrument, by default None

        Returns
        -------
        function
            The function associated to the given parameters
        """
        func = ae*nu + CurveFitModel.DHO(nu, be, a, nu0, gamma)
        if IR is not None: return np.convolve(func, IR, "same")
        return func
  

    @staticmethod
    def gaussian(nu, b, a, nu0, gamma, IR = None):
        """Model of a simple gaussian lineshape
        Parameters
        ----------
        nu : array
            The frequency array
        b : float
            The constant offset of the data
        a : float
            The amplitude of the peak
        nu0 : float
            The center position of the function 
        gamma : float
            The FWHM of the function
        IR : array, optional
            The impulse response of the instrument, by default None
        Returns
        -------
        function
            The function associated to the given parameters
        """
        _2_sigma_squared = gamma**2/(4*np.log(2))
        func = b + a*np.exp(-(nu-nu0)**2/(_2_sigma_squared))
        if IR is not None: return np.convolve(func, IR, "same")
        return func 


class BlsProcessingModels(Enum):
    Lorentzian = ("Lorentzian", CurveFitModel.lorentzian)
    LorentzianElastic = ("Lorentzian Elastic", CurveFitModel.lorentzian_elastic)
    DHO = ("DHO", CurveFitModel.DHO)
    DHOElastic = ("DHO Elastic", CurveFitModel.DHO_elastic)
    Gaussian = ("Gaussian", CurveFitModel.gaussian)

    @classmethod
    def to_param_dict(cls):
        return {m.label: m for m in cls}

    @property
    def func(self):
        return self.value[1]

    @property
    def label(self):
        return self.value[0]

    @property
    def signature(self):
        """Return an inspect.Signature object for the function."""
        return inspect.signature(self.func)

    @property
    def arguments(self):
        """Return an ordered dict of parameter names -> inspect.Parameter."""
        return self.signature.parameters

    @property
    def full_docstring(self):
        """Return the full docstring of the function."""
        return self.func.__doc__

    @property
    def short_docstring(self):
        """Return the first line of the docstring of the function."""
        if self.func.__doc__:
            return self.func.__doc__.strip().split("\n")[0]
        return ""

    @property
    def arguments_documentation(self) -> dict[str, str]:
        """
        Extract parameters and their descriptions from a NumPy-style docstring.
        Returns a dict {param_name: description}.
        """
        doc = self.full_docstring
        if not doc:
            return {}

        lines = doc.splitlines()
        params = {}
        in_params = False
        current_name = None
        buffer = []

        for line in lines:
            stripped = line.strip()

            # Detect "Parameters" section
            if stripped.lower().startswith("parameters"):
                in_params = True
                continue

            if in_params:
                # Section ends when we hit an empty line or another section (e.g. "Returns")
                if not stripped or stripped.lower().startswith("returns"):
                    if current_name:
                        params[current_name] = " ".join(buffer).strip()
                    break

                # Parameter definition line: "name : type"
                m = re.match(r"^(\w+)\s*:", stripped)
                if m:
                    # Save previous param
                    if current_name:
                        params[current_name] = " ".join(buffer).strip()
                    # Start new param
                    current_name = m.group(1)
                    buffer = []
                elif current_name:
                    # Description line (continuation)
                    buffer.append(stripped)

        return params

    def func_with_bls_args(self, x, shift, width, amplitude, offset):
        match self:
            case BlsProcessingModels.Lorentzian:
                return CurveFitModel.lorentzian(
                    nu=x, b=offset, a=amplitude, nu0=shift, gamma=width
                )
            case BlsProcessingModels.LorentzianElastic:
                raise Exception(
                    "Impossible to call LorentzianElastic: missing 'ae' argument"
                )
            case BlsProcessingModels.DHO:
                return CurveFitModel.DHO(
                    nu=x, b=offset, a=amplitude, nu0=shift, gamma=width
                )
            case BlsProcessingModels.Gaussian:
                return CurveFitModel.gaussian(
                    nu=x, b=offset, a=amplitude, nu0=shift, gamma=width
                )
            case BlsProcessingModels.DHOElastic:
                raise Exception("Impossible to call DHOElastic: missing 'ae' argument")
            case _:
                raise ValueError(f"Unknown model: {self}")

    @staticmethod
    def from_brimfile_models(model: bls_data.AnalysisResults.FitModel):
        brimfile_models = bls_data.AnalysisResults.FitModel
        match model:
            case brimfile_models.Undefined:
                raise Exception("Undefined function - can't continue")
            case brimfile_models.Lorentzian:
                return BlsProcessingModels.Lorentzian
            case brimfile_models.DHO:
                return BlsProcessingModels.DHO
            case brimfile_models.Gaussian:
                return BlsProcessingModels.Gaussian
            case brimfile_models.Voigt:
                raise Exception("Voigt function - not yet implemented")
            case brimfile_models.Custom:
                raise Exception("Custom function - not yet implemented")


class MultiPeakModel(param.Parameterized):
    base_model = param.ClassSelector(
        class_=BlsProcessingModels,
        default=BlsProcessingModels.Lorentzian,
        doc="Model to fit to the BLS spectrum. It's first parameter must be 'nu' (frequency).",
    )
    n_peaks = param.Integer(default=1, doc="Number of peaks to fit.")

    _multipeak_function = param.Callable()
    _param_names = param.List()

    def __init__(self, base_model: BlsProcessingModels, n_peaks: int, **params):
        super().__init__(**params)
        self.base_model = base_model
        self.n_peaks = n_peaks
        self._multipeak_function, self._param_names = self._create_multipeak_function()

    @property
    def label(self):
        return f"{self.n_peaks}x ({self.base_model.label})"

    @property
    def n_args(self):
        """
        Returns the number of arguments that the multipeak function expects

        For gaussian(nu, b, a, nu0, w) and n_peaks=2, it should return 8 (= 2 * len([b, a, nu0, w]))
        """
        return len(self._param_names) * self.n_peaks

    def _create_multipeak_function(self):
        """
        Creates a function that sums multiple instances of the base model.

        Each function instance will have its own set of parameters, for example:
        assuming the base_model has parameters {nu, b, a, nu0, w} (frequency, offset, amplitude, center frequency, width),
        then for n_peak=2, the resulting function will have parameters: {nu, b0, a0, nu00, w0, b1, a1, nu01, w1}

        """
        param_names = [
            p for p in list(self.base_model.arguments)[1:-1]
        ]  # Removing 'nu' (=x)

        def f(x, **params):
            y = np.zeros_like(x, dtype=float)
            for i in range(self.n_peaks):
                # build args for this peak
                kwargs = {}
                for name in param_names:  # skip baseline if shared
                    kwargs[name] = params[f"{name}{i}"]

                y += self.base_model.func(x, **kwargs)
            return y

        return f, param_names

    def _flatten_kwargs(self, kwargs: dict):
        """
        Converts from a dict with named parameters to a flat list of parameters.
        Example:
        { b0: 1, a0: 0.5, nu0: 10, w0: 2, b1: 0.8, a1: 0.3, nu1: 20, w1: 1 }
            -> [1, 0.5, 10, 2, 0.8, 0.3, 20, 1]

        If a parameter is missing, it defaults to 0.
        """
        flat = []
        for i in range(self.n_peaks):
            for name in self._param_names:
                flat.append(kwargs.get(f"{name}{i}", 0))
        return flat

    def _unflatten_args(self, args):
        """
        Converts from a flat list of parameters to a dict with named parameters.
        Example:
        [1, 0.5, 10, 2, 0.8, 0.3, 20, 1]
            -> { b0: 1, a0: 0.5, nu0: 10, w0: 2, b1: 0.8, a1: 0.3, nu1: 20, w1: 1 }
        """
        out = {}
        i = 0
        for p in range(self.n_peaks):
            for name in self._param_names:
                out[f"{name}{p}"] = args[i]
                i += 1
        return out

    def unflatten_args_grouped(self, args):
        """
        Convert flat args (list of floats) into a dict grouped by peak index.
        Example:
            [b0, a0, nu00, gamma0, b1, a1, nu01, gamma1]
        becomes:
            {"0": {"b": ..., "a": ..., "nu0": ..., "gamma": ...},
             "1": {"b": ..., "a": ..., "nu0": ..., "gamma": ...}}
        """
        out = {}
        i = 0
        for p in range(self.n_peaks):
            tmp_dict = {}
            for name in self._param_names:
                tmp_dict[name] = args[i]
                i += 1
            out[str(p)] = tmp_dict
        return out

    def function(self, x, **kwargs):
        """
        Evaluate the multi-peak model at given x values with provided parameters.

        Parameters
        ----------
        x : array-like
            The independent variable values where the model is evaluated.
        **kwargs : dict
            The parameters for each peak, named as { b0, a0, nu0, w0, b1, a1, nu1, w1, ... , bN, aN, nuN, wN}.,
        """
        out = self._multipeak_function(x, **kwargs)
        return out

    def function_flat(self, x, *args):
        """
        Evaluate the multi-peak model at given x values with provided parameters.

        Parameters
        ----------
        x : array-like
            The independent variable values where the model is evaluated.
        *args : list
            The parameters for each peak, named as [ b0, a0, nu0, w0, b1, a1, nu1, w1, ... , bN, aN, nuN, wN].,
        """
        kwargs = self._unflatten_args(args)
        out = self._multipeak_function(x, **kwargs)
        return out


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    base_model = BlsProcessingModels.DHO
    n_peaks = 3
    multipeak = MultiPeakModel(base_model=base_model, n_peaks=n_peaks)

    peaks = {
        "b0": 1,
        "a0": 0.5,
        "nu00": -5,
        "gamma0": 2,
        "b1": 0.8,
        "a1": 0.3,
        "nu01": 10,
        "gamma1": 1,
        "b2": 0.8,
        "a2": 0.3,
        "nu02": 15,
        "gamma2": 1,
    }
    x_range = np.linspace(-20, 20, 1000)
    y = multipeak.function(x_range, **peaks)
    plt.plot(x_range, y)
    plt.show()
