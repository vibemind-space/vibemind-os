function getDefaultExportFromCjs(x2) {
  return x2 && x2.__esModule && Object.prototype.hasOwnProperty.call(x2, "default") ? x2["default"] : x2;
}
var jsxRuntime = { exports: {} };
var reactJsxRuntime_production_min = {};
var react = { exports: {} };
var react_production_min = {};
/**
 * @license React
 * react.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */
var l$1 = Symbol.for("react.element"), n$1 = Symbol.for("react.portal"), p$2 = Symbol.for("react.fragment"), q$1 = Symbol.for("react.strict_mode"), r = Symbol.for("react.profiler"), t = Symbol.for("react.provider"), u = Symbol.for("react.context"), v$1 = Symbol.for("react.forward_ref"), w = Symbol.for("react.suspense"), x = Symbol.for("react.memo"), y = Symbol.for("react.lazy"), z$1 = Symbol.iterator;
function A$1(a) {
  if (null === a || "object" !== typeof a) return null;
  a = z$1 && a[z$1] || a["@@iterator"];
  return "function" === typeof a ? a : null;
}
var B$1 = { isMounted: function() {
  return false;
}, enqueueForceUpdate: function() {
}, enqueueReplaceState: function() {
}, enqueueSetState: function() {
} }, C$1 = Object.assign, D$1 = {};
function E$1(a, b, e) {
  this.props = a;
  this.context = b;
  this.refs = D$1;
  this.updater = e || B$1;
}
E$1.prototype.isReactComponent = {};
E$1.prototype.setState = function(a, b) {
  if ("object" !== typeof a && "function" !== typeof a && null != a) throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");
  this.updater.enqueueSetState(this, a, b, "setState");
};
E$1.prototype.forceUpdate = function(a) {
  this.updater.enqueueForceUpdate(this, a, "forceUpdate");
};
function F() {
}
F.prototype = E$1.prototype;
function G$1(a, b, e) {
  this.props = a;
  this.context = b;
  this.refs = D$1;
  this.updater = e || B$1;
}
var H$1 = G$1.prototype = new F();
H$1.constructor = G$1;
C$1(H$1, E$1.prototype);
H$1.isPureReactComponent = true;
var I$1 = Array.isArray, J = Object.prototype.hasOwnProperty, K$1 = { current: null }, L$1 = { key: true, ref: true, __self: true, __source: true };
function M$1(a, b, e) {
  var d, c = {}, k2 = null, h = null;
  if (null != b) for (d in void 0 !== b.ref && (h = b.ref), void 0 !== b.key && (k2 = "" + b.key), b) J.call(b, d) && !L$1.hasOwnProperty(d) && (c[d] = b[d]);
  var g = arguments.length - 2;
  if (1 === g) c.children = e;
  else if (1 < g) {
    for (var f2 = Array(g), m2 = 0; m2 < g; m2++) f2[m2] = arguments[m2 + 2];
    c.children = f2;
  }
  if (a && a.defaultProps) for (d in g = a.defaultProps, g) void 0 === c[d] && (c[d] = g[d]);
  return { $$typeof: l$1, type: a, key: k2, ref: h, props: c, _owner: K$1.current };
}
function N$1(a, b) {
  return { $$typeof: l$1, type: a.type, key: b, ref: a.ref, props: a.props, _owner: a._owner };
}
function O$1(a) {
  return "object" === typeof a && null !== a && a.$$typeof === l$1;
}
function escape(a) {
  var b = { "=": "=0", ":": "=2" };
  return "$" + a.replace(/[=:]/g, function(a2) {
    return b[a2];
  });
}
var P$1 = /\/+/g;
function Q$1(a, b) {
  return "object" === typeof a && null !== a && null != a.key ? escape("" + a.key) : b.toString(36);
}
function R$1(a, b, e, d, c) {
  var k2 = typeof a;
  if ("undefined" === k2 || "boolean" === k2) a = null;
  var h = false;
  if (null === a) h = true;
  else switch (k2) {
    case "string":
    case "number":
      h = true;
      break;
    case "object":
      switch (a.$$typeof) {
        case l$1:
        case n$1:
          h = true;
      }
  }
  if (h) return h = a, c = c(h), a = "" === d ? "." + Q$1(h, 0) : d, I$1(c) ? (e = "", null != a && (e = a.replace(P$1, "$&/") + "/"), R$1(c, b, e, "", function(a2) {
    return a2;
  })) : null != c && (O$1(c) && (c = N$1(c, e + (!c.key || h && h.key === c.key ? "" : ("" + c.key).replace(P$1, "$&/") + "/") + a)), b.push(c)), 1;
  h = 0;
  d = "" === d ? "." : d + ":";
  if (I$1(a)) for (var g = 0; g < a.length; g++) {
    k2 = a[g];
    var f2 = d + Q$1(k2, g);
    h += R$1(k2, b, e, f2, c);
  }
  else if (f2 = A$1(a), "function" === typeof f2) for (a = f2.call(a), g = 0; !(k2 = a.next()).done; ) k2 = k2.value, f2 = d + Q$1(k2, g++), h += R$1(k2, b, e, f2, c);
  else if ("object" === k2) throw b = String(a), Error("Objects are not valid as a React child (found: " + ("[object Object]" === b ? "object with keys {" + Object.keys(a).join(", ") + "}" : b) + "). If you meant to render a collection of children, use an array instead.");
  return h;
}
function S$1(a, b, e) {
  if (null == a) return a;
  var d = [], c = 0;
  R$1(a, d, "", "", function(a2) {
    return b.call(e, a2, c++);
  });
  return d;
}
function T$1(a) {
  if (-1 === a._status) {
    var b = a._result;
    b = b();
    b.then(function(b2) {
      if (0 === a._status || -1 === a._status) a._status = 1, a._result = b2;
    }, function(b2) {
      if (0 === a._status || -1 === a._status) a._status = 2, a._result = b2;
    });
    -1 === a._status && (a._status = 0, a._result = b);
  }
  if (1 === a._status) return a._result.default;
  throw a._result;
}
var U$1 = { current: null }, V$1 = { transition: null }, W$1 = { ReactCurrentDispatcher: U$1, ReactCurrentBatchConfig: V$1, ReactCurrentOwner: K$1 };
function X$2() {
  throw Error("act(...) is not supported in production builds of React.");
}
react_production_min.Children = { map: S$1, forEach: function(a, b, e) {
  S$1(a, function() {
    b.apply(this, arguments);
  }, e);
}, count: function(a) {
  var b = 0;
  S$1(a, function() {
    b++;
  });
  return b;
}, toArray: function(a) {
  return S$1(a, function(a2) {
    return a2;
  }) || [];
}, only: function(a) {
  if (!O$1(a)) throw Error("React.Children.only expected to receive a single React element child.");
  return a;
} };
react_production_min.Component = E$1;
react_production_min.Fragment = p$2;
react_production_min.Profiler = r;
react_production_min.PureComponent = G$1;
react_production_min.StrictMode = q$1;
react_production_min.Suspense = w;
react_production_min.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = W$1;
react_production_min.act = X$2;
react_production_min.cloneElement = function(a, b, e) {
  if (null === a || void 0 === a) throw Error("React.cloneElement(...): The argument must be a React element, but you passed " + a + ".");
  var d = C$1({}, a.props), c = a.key, k2 = a.ref, h = a._owner;
  if (null != b) {
    void 0 !== b.ref && (k2 = b.ref, h = K$1.current);
    void 0 !== b.key && (c = "" + b.key);
    if (a.type && a.type.defaultProps) var g = a.type.defaultProps;
    for (f2 in b) J.call(b, f2) && !L$1.hasOwnProperty(f2) && (d[f2] = void 0 === b[f2] && void 0 !== g ? g[f2] : b[f2]);
  }
  var f2 = arguments.length - 2;
  if (1 === f2) d.children = e;
  else if (1 < f2) {
    g = Array(f2);
    for (var m2 = 0; m2 < f2; m2++) g[m2] = arguments[m2 + 2];
    d.children = g;
  }
  return { $$typeof: l$1, type: a.type, key: c, ref: k2, props: d, _owner: h };
};
react_production_min.createContext = function(a) {
  a = { $$typeof: u, _currentValue: a, _currentValue2: a, _threadCount: 0, Provider: null, Consumer: null, _defaultValue: null, _globalName: null };
  a.Provider = { $$typeof: t, _context: a };
  return a.Consumer = a;
};
react_production_min.createElement = M$1;
react_production_min.createFactory = function(a) {
  var b = M$1.bind(null, a);
  b.type = a;
  return b;
};
react_production_min.createRef = function() {
  return { current: null };
};
react_production_min.forwardRef = function(a) {
  return { $$typeof: v$1, render: a };
};
react_production_min.isValidElement = O$1;
react_production_min.lazy = function(a) {
  return { $$typeof: y, _payload: { _status: -1, _result: a }, _init: T$1 };
};
react_production_min.memo = function(a, b) {
  return { $$typeof: x, type: a, compare: void 0 === b ? null : b };
};
react_production_min.startTransition = function(a) {
  var b = V$1.transition;
  V$1.transition = {};
  try {
    a();
  } finally {
    V$1.transition = b;
  }
};
react_production_min.unstable_act = X$2;
react_production_min.useCallback = function(a, b) {
  return U$1.current.useCallback(a, b);
};
react_production_min.useContext = function(a) {
  return U$1.current.useContext(a);
};
react_production_min.useDebugValue = function() {
};
react_production_min.useDeferredValue = function(a) {
  return U$1.current.useDeferredValue(a);
};
react_production_min.useEffect = function(a, b) {
  return U$1.current.useEffect(a, b);
};
react_production_min.useId = function() {
  return U$1.current.useId();
};
react_production_min.useImperativeHandle = function(a, b, e) {
  return U$1.current.useImperativeHandle(a, b, e);
};
react_production_min.useInsertionEffect = function(a, b) {
  return U$1.current.useInsertionEffect(a, b);
};
react_production_min.useLayoutEffect = function(a, b) {
  return U$1.current.useLayoutEffect(a, b);
};
react_production_min.useMemo = function(a, b) {
  return U$1.current.useMemo(a, b);
};
react_production_min.useReducer = function(a, b, e) {
  return U$1.current.useReducer(a, b, e);
};
react_production_min.useRef = function(a) {
  return U$1.current.useRef(a);
};
react_production_min.useState = function(a) {
  return U$1.current.useState(a);
};
react_production_min.useSyncExternalStore = function(a, b, e) {
  return U$1.current.useSyncExternalStore(a, b, e);
};
react_production_min.useTransition = function() {
  return U$1.current.useTransition();
};
react_production_min.version = "18.3.1";
{
  react.exports = react_production_min;
}
var reactExports = react.exports;
const React$2 = /* @__PURE__ */ getDefaultExportFromCjs(reactExports);
/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */
var f = reactExports, k = Symbol.for("react.element"), l = Symbol.for("react.fragment"), m$1 = Object.prototype.hasOwnProperty, n = f.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner, p$1 = { key: true, ref: true, __self: true, __source: true };
function q(c, a, g) {
  var b, d = {}, e = null, h = null;
  void 0 !== g && (e = "" + g);
  void 0 !== a.key && (e = "" + a.key);
  void 0 !== a.ref && (h = a.ref);
  for (b in a) m$1.call(a, b) && !p$1.hasOwnProperty(b) && (d[b] = a[b]);
  if (c && c.defaultProps) for (b in a = c.defaultProps, a) void 0 === d[b] && (d[b] = a[b]);
  return { $$typeof: k, type: c, key: e, ref: h, props: d, _owner: n.current };
}
reactJsxRuntime_production_min.Fragment = l;
reactJsxRuntime_production_min.jsx = q;
reactJsxRuntime_production_min.jsxs = q;
{
  jsxRuntime.exports = reactJsxRuntime_production_min;
}
var jsxRuntimeExports = jsxRuntime.exports;
var client = {};
var reactDom = { exports: {} };
var reactDom_production_min = {};
var scheduler = { exports: {} };
var scheduler_production_min = {};
/**
 * @license React
 * scheduler.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */
(function(exports$1) {
  function f2(a, b) {
    var c = a.length;
    a.push(b);
    a: for (; 0 < c; ) {
      var d = c - 1 >>> 1, e = a[d];
      if (0 < g(e, b)) a[d] = b, a[c] = e, c = d;
      else break a;
    }
  }
  function h(a) {
    return 0 === a.length ? null : a[0];
  }
  function k2(a) {
    if (0 === a.length) return null;
    var b = a[0], c = a.pop();
    if (c !== b) {
      a[0] = c;
      a: for (var d = 0, e = a.length, w2 = e >>> 1; d < w2; ) {
        var m2 = 2 * (d + 1) - 1, C2 = a[m2], n2 = m2 + 1, x2 = a[n2];
        if (0 > g(C2, c)) n2 < e && 0 > g(x2, C2) ? (a[d] = x2, a[n2] = c, d = n2) : (a[d] = C2, a[m2] = c, d = m2);
        else if (n2 < e && 0 > g(x2, c)) a[d] = x2, a[n2] = c, d = n2;
        else break a;
      }
    }
    return b;
  }
  function g(a, b) {
    var c = a.sortIndex - b.sortIndex;
    return 0 !== c ? c : a.id - b.id;
  }
  if ("object" === typeof performance && "function" === typeof performance.now) {
    var l2 = performance;
    exports$1.unstable_now = function() {
      return l2.now();
    };
  } else {
    var p2 = Date, q2 = p2.now();
    exports$1.unstable_now = function() {
      return p2.now() - q2;
    };
  }
  var r2 = [], t2 = [], u2 = 1, v2 = null, y2 = 3, z2 = false, A2 = false, B2 = false, D2 = "function" === typeof setTimeout ? setTimeout : null, E2 = "function" === typeof clearTimeout ? clearTimeout : null, F2 = "undefined" !== typeof setImmediate ? setImmediate : null;
  "undefined" !== typeof navigator && void 0 !== navigator.scheduling && void 0 !== navigator.scheduling.isInputPending && navigator.scheduling.isInputPending.bind(navigator.scheduling);
  function G2(a) {
    for (var b = h(t2); null !== b; ) {
      if (null === b.callback) k2(t2);
      else if (b.startTime <= a) k2(t2), b.sortIndex = b.expirationTime, f2(r2, b);
      else break;
      b = h(t2);
    }
  }
  function H2(a) {
    B2 = false;
    G2(a);
    if (!A2) if (null !== h(r2)) A2 = true, I2(J2);
    else {
      var b = h(t2);
      null !== b && K2(H2, b.startTime - a);
    }
  }
  function J2(a, b) {
    A2 = false;
    B2 && (B2 = false, E2(L2), L2 = -1);
    z2 = true;
    var c = y2;
    try {
      G2(b);
      for (v2 = h(r2); null !== v2 && (!(v2.expirationTime > b) || a && !M2()); ) {
        var d = v2.callback;
        if ("function" === typeof d) {
          v2.callback = null;
          y2 = v2.priorityLevel;
          var e = d(v2.expirationTime <= b);
          b = exports$1.unstable_now();
          "function" === typeof e ? v2.callback = e : v2 === h(r2) && k2(r2);
          G2(b);
        } else k2(r2);
        v2 = h(r2);
      }
      if (null !== v2) var w2 = true;
      else {
        var m2 = h(t2);
        null !== m2 && K2(H2, m2.startTime - b);
        w2 = false;
      }
      return w2;
    } finally {
      v2 = null, y2 = c, z2 = false;
    }
  }
  var N2 = false, O2 = null, L2 = -1, P2 = 5, Q2 = -1;
  function M2() {
    return exports$1.unstable_now() - Q2 < P2 ? false : true;
  }
  function R2() {
    if (null !== O2) {
      var a = exports$1.unstable_now();
      Q2 = a;
      var b = true;
      try {
        b = O2(true, a);
      } finally {
        b ? S2() : (N2 = false, O2 = null);
      }
    } else N2 = false;
  }
  var S2;
  if ("function" === typeof F2) S2 = function() {
    F2(R2);
  };
  else if ("undefined" !== typeof MessageChannel) {
    var T2 = new MessageChannel(), U2 = T2.port2;
    T2.port1.onmessage = R2;
    S2 = function() {
      U2.postMessage(null);
    };
  } else S2 = function() {
    D2(R2, 0);
  };
  function I2(a) {
    O2 = a;
    N2 || (N2 = true, S2());
  }
  function K2(a, b) {
    L2 = D2(function() {
      a(exports$1.unstable_now());
    }, b);
  }
  exports$1.unstable_IdlePriority = 5;
  exports$1.unstable_ImmediatePriority = 1;
  exports$1.unstable_LowPriority = 4;
  exports$1.unstable_NormalPriority = 3;
  exports$1.unstable_Profiling = null;
  exports$1.unstable_UserBlockingPriority = 2;
  exports$1.unstable_cancelCallback = function(a) {
    a.callback = null;
  };
  exports$1.unstable_continueExecution = function() {
    A2 || z2 || (A2 = true, I2(J2));
  };
  exports$1.unstable_forceFrameRate = function(a) {
    0 > a || 125 < a ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : P2 = 0 < a ? Math.floor(1e3 / a) : 5;
  };
  exports$1.unstable_getCurrentPriorityLevel = function() {
    return y2;
  };
  exports$1.unstable_getFirstCallbackNode = function() {
    return h(r2);
  };
  exports$1.unstable_next = function(a) {
    switch (y2) {
      case 1:
      case 2:
      case 3:
        var b = 3;
        break;
      default:
        b = y2;
    }
    var c = y2;
    y2 = b;
    try {
      return a();
    } finally {
      y2 = c;
    }
  };
  exports$1.unstable_pauseExecution = function() {
  };
  exports$1.unstable_requestPaint = function() {
  };
  exports$1.unstable_runWithPriority = function(a, b) {
    switch (a) {
      case 1:
      case 2:
      case 3:
      case 4:
      case 5:
        break;
      default:
        a = 3;
    }
    var c = y2;
    y2 = a;
    try {
      return b();
    } finally {
      y2 = c;
    }
  };
  exports$1.unstable_scheduleCallback = function(a, b, c) {
    var d = exports$1.unstable_now();
    "object" === typeof c && null !== c ? (c = c.delay, c = "number" === typeof c && 0 < c ? d + c : d) : c = d;
    switch (a) {
      case 1:
        var e = -1;
        break;
      case 2:
        e = 250;
        break;
      case 5:
        e = 1073741823;
        break;
      case 4:
        e = 1e4;
        break;
      default:
        e = 5e3;
    }
    e = c + e;
    a = { id: u2++, callback: b, priorityLevel: a, startTime: c, expirationTime: e, sortIndex: -1 };
    c > d ? (a.sortIndex = c, f2(t2, a), null === h(r2) && a === h(t2) && (B2 ? (E2(L2), L2 = -1) : B2 = true, K2(H2, c - d))) : (a.sortIndex = e, f2(r2, a), A2 || z2 || (A2 = true, I2(J2)));
    return a;
  };
  exports$1.unstable_shouldYield = M2;
  exports$1.unstable_wrapCallback = function(a) {
    var b = y2;
    return function() {
      var c = y2;
      y2 = b;
      try {
        return a.apply(this, arguments);
      } finally {
        y2 = c;
      }
    };
  };
})(scheduler_production_min);
{
  scheduler.exports = scheduler_production_min;
}
var schedulerExports = scheduler.exports;
/**
 * @license React
 * react-dom.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */
var aa = reactExports, ca = schedulerExports;
function p(a) {
  for (var b = "https://reactjs.org/docs/error-decoder.html?invariant=" + a, c = 1; c < arguments.length; c++) b += "&args[]=" + encodeURIComponent(arguments[c]);
  return "Minified React error #" + a + "; visit " + b + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
}
var da = /* @__PURE__ */ new Set(), ea = {};
function fa(a, b) {
  ha(a, b);
  ha(a + "Capture", b);
}
function ha(a, b) {
  ea[a] = b;
  for (a = 0; a < b.length; a++) da.add(b[a]);
}
var ia = !("undefined" === typeof window || "undefined" === typeof window.document || "undefined" === typeof window.document.createElement), ja = Object.prototype.hasOwnProperty, ka = /^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/, la = {}, ma = {};
function oa(a) {
  if (ja.call(ma, a)) return true;
  if (ja.call(la, a)) return false;
  if (ka.test(a)) return ma[a] = true;
  la[a] = true;
  return false;
}
function pa(a, b, c, d) {
  if (null !== c && 0 === c.type) return false;
  switch (typeof b) {
    case "function":
    case "symbol":
      return true;
    case "boolean":
      if (d) return false;
      if (null !== c) return !c.acceptsBooleans;
      a = a.toLowerCase().slice(0, 5);
      return "data-" !== a && "aria-" !== a;
    default:
      return false;
  }
}
function qa(a, b, c, d) {
  if (null === b || "undefined" === typeof b || pa(a, b, c, d)) return true;
  if (d) return false;
  if (null !== c) switch (c.type) {
    case 3:
      return !b;
    case 4:
      return false === b;
    case 5:
      return isNaN(b);
    case 6:
      return isNaN(b) || 1 > b;
  }
  return false;
}
function v(a, b, c, d, e, f2, g) {
  this.acceptsBooleans = 2 === b || 3 === b || 4 === b;
  this.attributeName = d;
  this.attributeNamespace = e;
  this.mustUseProperty = c;
  this.propertyName = a;
  this.type = b;
  this.sanitizeURL = f2;
  this.removeEmptyString = g;
}
var z = {};
"children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(a) {
  z[a] = new v(a, 0, false, a, null, false, false);
});
[["acceptCharset", "accept-charset"], ["className", "class"], ["htmlFor", "for"], ["httpEquiv", "http-equiv"]].forEach(function(a) {
  var b = a[0];
  z[b] = new v(b, 1, false, a[1], null, false, false);
});
["contentEditable", "draggable", "spellCheck", "value"].forEach(function(a) {
  z[a] = new v(a, 2, false, a.toLowerCase(), null, false, false);
});
["autoReverse", "externalResourcesRequired", "focusable", "preserveAlpha"].forEach(function(a) {
  z[a] = new v(a, 2, false, a, null, false, false);
});
"allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(a) {
  z[a] = new v(a, 3, false, a.toLowerCase(), null, false, false);
});
["checked", "multiple", "muted", "selected"].forEach(function(a) {
  z[a] = new v(a, 3, true, a, null, false, false);
});
["capture", "download"].forEach(function(a) {
  z[a] = new v(a, 4, false, a, null, false, false);
});
["cols", "rows", "size", "span"].forEach(function(a) {
  z[a] = new v(a, 6, false, a, null, false, false);
});
["rowSpan", "start"].forEach(function(a) {
  z[a] = new v(a, 5, false, a.toLowerCase(), null, false, false);
});
var ra = /[\-:]([a-z])/g;
function sa(a) {
  return a[1].toUpperCase();
}
"accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(a) {
  var b = a.replace(
    ra,
    sa
  );
  z[b] = new v(b, 1, false, a, null, false, false);
});
"xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(a) {
  var b = a.replace(ra, sa);
  z[b] = new v(b, 1, false, a, "http://www.w3.org/1999/xlink", false, false);
});
["xml:base", "xml:lang", "xml:space"].forEach(function(a) {
  var b = a.replace(ra, sa);
  z[b] = new v(b, 1, false, a, "http://www.w3.org/XML/1998/namespace", false, false);
});
["tabIndex", "crossOrigin"].forEach(function(a) {
  z[a] = new v(a, 1, false, a.toLowerCase(), null, false, false);
});
z.xlinkHref = new v("xlinkHref", 1, false, "xlink:href", "http://www.w3.org/1999/xlink", true, false);
["src", "href", "action", "formAction"].forEach(function(a) {
  z[a] = new v(a, 1, false, a.toLowerCase(), null, true, true);
});
function ta(a, b, c, d) {
  var e = z.hasOwnProperty(b) ? z[b] : null;
  if (null !== e ? 0 !== e.type : d || !(2 < b.length) || "o" !== b[0] && "O" !== b[0] || "n" !== b[1] && "N" !== b[1]) qa(b, c, e, d) && (c = null), d || null === e ? oa(b) && (null === c ? a.removeAttribute(b) : a.setAttribute(b, "" + c)) : e.mustUseProperty ? a[e.propertyName] = null === c ? 3 === e.type ? false : "" : c : (b = e.attributeName, d = e.attributeNamespace, null === c ? a.removeAttribute(b) : (e = e.type, c = 3 === e || 4 === e && true === c ? "" : "" + c, d ? a.setAttributeNS(d, b, c) : a.setAttribute(b, c)));
}
var ua = aa.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED, va = Symbol.for("react.element"), wa = Symbol.for("react.portal"), ya = Symbol.for("react.fragment"), za = Symbol.for("react.strict_mode"), Aa = Symbol.for("react.profiler"), Ba = Symbol.for("react.provider"), Ca = Symbol.for("react.context"), Da = Symbol.for("react.forward_ref"), Ea = Symbol.for("react.suspense"), Fa = Symbol.for("react.suspense_list"), Ga = Symbol.for("react.memo"), Ha = Symbol.for("react.lazy");
var Ia = Symbol.for("react.offscreen");
var Ja = Symbol.iterator;
function Ka(a) {
  if (null === a || "object" !== typeof a) return null;
  a = Ja && a[Ja] || a["@@iterator"];
  return "function" === typeof a ? a : null;
}
var A = Object.assign, La;
function Ma(a) {
  if (void 0 === La) try {
    throw Error();
  } catch (c) {
    var b = c.stack.trim().match(/\n( *(at )?)/);
    La = b && b[1] || "";
  }
  return "\n" + La + a;
}
var Na = false;
function Oa(a, b) {
  if (!a || Na) return "";
  Na = true;
  var c = Error.prepareStackTrace;
  Error.prepareStackTrace = void 0;
  try {
    if (b) if (b = function() {
      throw Error();
    }, Object.defineProperty(b.prototype, "props", { set: function() {
      throw Error();
    } }), "object" === typeof Reflect && Reflect.construct) {
      try {
        Reflect.construct(b, []);
      } catch (l2) {
        var d = l2;
      }
      Reflect.construct(a, [], b);
    } else {
      try {
        b.call();
      } catch (l2) {
        d = l2;
      }
      a.call(b.prototype);
    }
    else {
      try {
        throw Error();
      } catch (l2) {
        d = l2;
      }
      a();
    }
  } catch (l2) {
    if (l2 && d && "string" === typeof l2.stack) {
      for (var e = l2.stack.split("\n"), f2 = d.stack.split("\n"), g = e.length - 1, h = f2.length - 1; 1 <= g && 0 <= h && e[g] !== f2[h]; ) h--;
      for (; 1 <= g && 0 <= h; g--, h--) if (e[g] !== f2[h]) {
        if (1 !== g || 1 !== h) {
          do
            if (g--, h--, 0 > h || e[g] !== f2[h]) {
              var k2 = "\n" + e[g].replace(" at new ", " at ");
              a.displayName && k2.includes("<anonymous>") && (k2 = k2.replace("<anonymous>", a.displayName));
              return k2;
            }
          while (1 <= g && 0 <= h);
        }
        break;
      }
    }
  } finally {
    Na = false, Error.prepareStackTrace = c;
  }
  return (a = a ? a.displayName || a.name : "") ? Ma(a) : "";
}
function Pa(a) {
  switch (a.tag) {
    case 5:
      return Ma(a.type);
    case 16:
      return Ma("Lazy");
    case 13:
      return Ma("Suspense");
    case 19:
      return Ma("SuspenseList");
    case 0:
    case 2:
    case 15:
      return a = Oa(a.type, false), a;
    case 11:
      return a = Oa(a.type.render, false), a;
    case 1:
      return a = Oa(a.type, true), a;
    default:
      return "";
  }
}
function Qa(a) {
  if (null == a) return null;
  if ("function" === typeof a) return a.displayName || a.name || null;
  if ("string" === typeof a) return a;
  switch (a) {
    case ya:
      return "Fragment";
    case wa:
      return "Portal";
    case Aa:
      return "Profiler";
    case za:
      return "StrictMode";
    case Ea:
      return "Suspense";
    case Fa:
      return "SuspenseList";
  }
  if ("object" === typeof a) switch (a.$$typeof) {
    case Ca:
      return (a.displayName || "Context") + ".Consumer";
    case Ba:
      return (a._context.displayName || "Context") + ".Provider";
    case Da:
      var b = a.render;
      a = a.displayName;
      a || (a = b.displayName || b.name || "", a = "" !== a ? "ForwardRef(" + a + ")" : "ForwardRef");
      return a;
    case Ga:
      return b = a.displayName || null, null !== b ? b : Qa(a.type) || "Memo";
    case Ha:
      b = a._payload;
      a = a._init;
      try {
        return Qa(a(b));
      } catch (c) {
      }
  }
  return null;
}
function Ra(a) {
  var b = a.type;
  switch (a.tag) {
    case 24:
      return "Cache";
    case 9:
      return (b.displayName || "Context") + ".Consumer";
    case 10:
      return (b._context.displayName || "Context") + ".Provider";
    case 18:
      return "DehydratedFragment";
    case 11:
      return a = b.render, a = a.displayName || a.name || "", b.displayName || ("" !== a ? "ForwardRef(" + a + ")" : "ForwardRef");
    case 7:
      return "Fragment";
    case 5:
      return b;
    case 4:
      return "Portal";
    case 3:
      return "Root";
    case 6:
      return "Text";
    case 16:
      return Qa(b);
    case 8:
      return b === za ? "StrictMode" : "Mode";
    case 22:
      return "Offscreen";
    case 12:
      return "Profiler";
    case 21:
      return "Scope";
    case 13:
      return "Suspense";
    case 19:
      return "SuspenseList";
    case 25:
      return "TracingMarker";
    case 1:
    case 0:
    case 17:
    case 2:
    case 14:
    case 15:
      if ("function" === typeof b) return b.displayName || b.name || null;
      if ("string" === typeof b) return b;
  }
  return null;
}
function Sa(a) {
  switch (typeof a) {
    case "boolean":
    case "number":
    case "string":
    case "undefined":
      return a;
    case "object":
      return a;
    default:
      return "";
  }
}
function Ta(a) {
  var b = a.type;
  return (a = a.nodeName) && "input" === a.toLowerCase() && ("checkbox" === b || "radio" === b);
}
function Ua(a) {
  var b = Ta(a) ? "checked" : "value", c = Object.getOwnPropertyDescriptor(a.constructor.prototype, b), d = "" + a[b];
  if (!a.hasOwnProperty(b) && "undefined" !== typeof c && "function" === typeof c.get && "function" === typeof c.set) {
    var e = c.get, f2 = c.set;
    Object.defineProperty(a, b, { configurable: true, get: function() {
      return e.call(this);
    }, set: function(a2) {
      d = "" + a2;
      f2.call(this, a2);
    } });
    Object.defineProperty(a, b, { enumerable: c.enumerable });
    return { getValue: function() {
      return d;
    }, setValue: function(a2) {
      d = "" + a2;
    }, stopTracking: function() {
      a._valueTracker = null;
      delete a[b];
    } };
  }
}
function Va(a) {
  a._valueTracker || (a._valueTracker = Ua(a));
}
function Wa(a) {
  if (!a) return false;
  var b = a._valueTracker;
  if (!b) return true;
  var c = b.getValue();
  var d = "";
  a && (d = Ta(a) ? a.checked ? "true" : "false" : a.value);
  a = d;
  return a !== c ? (b.setValue(a), true) : false;
}
function Xa(a) {
  a = a || ("undefined" !== typeof document ? document : void 0);
  if ("undefined" === typeof a) return null;
  try {
    return a.activeElement || a.body;
  } catch (b) {
    return a.body;
  }
}
function Ya(a, b) {
  var c = b.checked;
  return A({}, b, { defaultChecked: void 0, defaultValue: void 0, value: void 0, checked: null != c ? c : a._wrapperState.initialChecked });
}
function Za(a, b) {
  var c = null == b.defaultValue ? "" : b.defaultValue, d = null != b.checked ? b.checked : b.defaultChecked;
  c = Sa(null != b.value ? b.value : c);
  a._wrapperState = { initialChecked: d, initialValue: c, controlled: "checkbox" === b.type || "radio" === b.type ? null != b.checked : null != b.value };
}
function ab(a, b) {
  b = b.checked;
  null != b && ta(a, "checked", b, false);
}
function bb(a, b) {
  ab(a, b);
  var c = Sa(b.value), d = b.type;
  if (null != c) if ("number" === d) {
    if (0 === c && "" === a.value || a.value != c) a.value = "" + c;
  } else a.value !== "" + c && (a.value = "" + c);
  else if ("submit" === d || "reset" === d) {
    a.removeAttribute("value");
    return;
  }
  b.hasOwnProperty("value") ? cb(a, b.type, c) : b.hasOwnProperty("defaultValue") && cb(a, b.type, Sa(b.defaultValue));
  null == b.checked && null != b.defaultChecked && (a.defaultChecked = !!b.defaultChecked);
}
function db(a, b, c) {
  if (b.hasOwnProperty("value") || b.hasOwnProperty("defaultValue")) {
    var d = b.type;
    if (!("submit" !== d && "reset" !== d || void 0 !== b.value && null !== b.value)) return;
    b = "" + a._wrapperState.initialValue;
    c || b === a.value || (a.value = b);
    a.defaultValue = b;
  }
  c = a.name;
  "" !== c && (a.name = "");
  a.defaultChecked = !!a._wrapperState.initialChecked;
  "" !== c && (a.name = c);
}
function cb(a, b, c) {
  if ("number" !== b || Xa(a.ownerDocument) !== a) null == c ? a.defaultValue = "" + a._wrapperState.initialValue : a.defaultValue !== "" + c && (a.defaultValue = "" + c);
}
var eb = Array.isArray;
function fb(a, b, c, d) {
  a = a.options;
  if (b) {
    b = {};
    for (var e = 0; e < c.length; e++) b["$" + c[e]] = true;
    for (c = 0; c < a.length; c++) e = b.hasOwnProperty("$" + a[c].value), a[c].selected !== e && (a[c].selected = e), e && d && (a[c].defaultSelected = true);
  } else {
    c = "" + Sa(c);
    b = null;
    for (e = 0; e < a.length; e++) {
      if (a[e].value === c) {
        a[e].selected = true;
        d && (a[e].defaultSelected = true);
        return;
      }
      null !== b || a[e].disabled || (b = a[e]);
    }
    null !== b && (b.selected = true);
  }
}
function gb(a, b) {
  if (null != b.dangerouslySetInnerHTML) throw Error(p(91));
  return A({}, b, { value: void 0, defaultValue: void 0, children: "" + a._wrapperState.initialValue });
}
function hb(a, b) {
  var c = b.value;
  if (null == c) {
    c = b.children;
    b = b.defaultValue;
    if (null != c) {
      if (null != b) throw Error(p(92));
      if (eb(c)) {
        if (1 < c.length) throw Error(p(93));
        c = c[0];
      }
      b = c;
    }
    null == b && (b = "");
    c = b;
  }
  a._wrapperState = { initialValue: Sa(c) };
}
function ib(a, b) {
  var c = Sa(b.value), d = Sa(b.defaultValue);
  null != c && (c = "" + c, c !== a.value && (a.value = c), null == b.defaultValue && a.defaultValue !== c && (a.defaultValue = c));
  null != d && (a.defaultValue = "" + d);
}
function jb(a) {
  var b = a.textContent;
  b === a._wrapperState.initialValue && "" !== b && null !== b && (a.value = b);
}
function kb(a) {
  switch (a) {
    case "svg":
      return "http://www.w3.org/2000/svg";
    case "math":
      return "http://www.w3.org/1998/Math/MathML";
    default:
      return "http://www.w3.org/1999/xhtml";
  }
}
function lb(a, b) {
  return null == a || "http://www.w3.org/1999/xhtml" === a ? kb(b) : "http://www.w3.org/2000/svg" === a && "foreignObject" === b ? "http://www.w3.org/1999/xhtml" : a;
}
var mb, nb = function(a) {
  return "undefined" !== typeof MSApp && MSApp.execUnsafeLocalFunction ? function(b, c, d, e) {
    MSApp.execUnsafeLocalFunction(function() {
      return a(b, c, d, e);
    });
  } : a;
}(function(a, b) {
  if ("http://www.w3.org/2000/svg" !== a.namespaceURI || "innerHTML" in a) a.innerHTML = b;
  else {
    mb = mb || document.createElement("div");
    mb.innerHTML = "<svg>" + b.valueOf().toString() + "</svg>";
    for (b = mb.firstChild; a.firstChild; ) a.removeChild(a.firstChild);
    for (; b.firstChild; ) a.appendChild(b.firstChild);
  }
});
function ob(a, b) {
  if (b) {
    var c = a.firstChild;
    if (c && c === a.lastChild && 3 === c.nodeType) {
      c.nodeValue = b;
      return;
    }
  }
  a.textContent = b;
}
var pb = {
  animationIterationCount: true,
  aspectRatio: true,
  borderImageOutset: true,
  borderImageSlice: true,
  borderImageWidth: true,
  boxFlex: true,
  boxFlexGroup: true,
  boxOrdinalGroup: true,
  columnCount: true,
  columns: true,
  flex: true,
  flexGrow: true,
  flexPositive: true,
  flexShrink: true,
  flexNegative: true,
  flexOrder: true,
  gridArea: true,
  gridRow: true,
  gridRowEnd: true,
  gridRowSpan: true,
  gridRowStart: true,
  gridColumn: true,
  gridColumnEnd: true,
  gridColumnSpan: true,
  gridColumnStart: true,
  fontWeight: true,
  lineClamp: true,
  lineHeight: true,
  opacity: true,
  order: true,
  orphans: true,
  tabSize: true,
  widows: true,
  zIndex: true,
  zoom: true,
  fillOpacity: true,
  floodOpacity: true,
  stopOpacity: true,
  strokeDasharray: true,
  strokeDashoffset: true,
  strokeMiterlimit: true,
  strokeOpacity: true,
  strokeWidth: true
}, qb = ["Webkit", "ms", "Moz", "O"];
Object.keys(pb).forEach(function(a) {
  qb.forEach(function(b) {
    b = b + a.charAt(0).toUpperCase() + a.substring(1);
    pb[b] = pb[a];
  });
});
function rb(a, b, c) {
  return null == b || "boolean" === typeof b || "" === b ? "" : c || "number" !== typeof b || 0 === b || pb.hasOwnProperty(a) && pb[a] ? ("" + b).trim() : b + "px";
}
function sb(a, b) {
  a = a.style;
  for (var c in b) if (b.hasOwnProperty(c)) {
    var d = 0 === c.indexOf("--"), e = rb(c, b[c], d);
    "float" === c && (c = "cssFloat");
    d ? a.setProperty(c, e) : a[c] = e;
  }
}
var tb = A({ menuitem: true }, { area: true, base: true, br: true, col: true, embed: true, hr: true, img: true, input: true, keygen: true, link: true, meta: true, param: true, source: true, track: true, wbr: true });
function ub(a, b) {
  if (b) {
    if (tb[a] && (null != b.children || null != b.dangerouslySetInnerHTML)) throw Error(p(137, a));
    if (null != b.dangerouslySetInnerHTML) {
      if (null != b.children) throw Error(p(60));
      if ("object" !== typeof b.dangerouslySetInnerHTML || !("__html" in b.dangerouslySetInnerHTML)) throw Error(p(61));
    }
    if (null != b.style && "object" !== typeof b.style) throw Error(p(62));
  }
}
function vb(a, b) {
  if (-1 === a.indexOf("-")) return "string" === typeof b.is;
  switch (a) {
    case "annotation-xml":
    case "color-profile":
    case "font-face":
    case "font-face-src":
    case "font-face-uri":
    case "font-face-format":
    case "font-face-name":
    case "missing-glyph":
      return false;
    default:
      return true;
  }
}
var wb = null;
function xb(a) {
  a = a.target || a.srcElement || window;
  a.correspondingUseElement && (a = a.correspondingUseElement);
  return 3 === a.nodeType ? a.parentNode : a;
}
var yb = null, zb = null, Ab = null;
function Bb(a) {
  if (a = Cb(a)) {
    if ("function" !== typeof yb) throw Error(p(280));
    var b = a.stateNode;
    b && (b = Db(b), yb(a.stateNode, a.type, b));
  }
}
function Eb(a) {
  zb ? Ab ? Ab.push(a) : Ab = [a] : zb = a;
}
function Fb() {
  if (zb) {
    var a = zb, b = Ab;
    Ab = zb = null;
    Bb(a);
    if (b) for (a = 0; a < b.length; a++) Bb(b[a]);
  }
}
function Gb(a, b) {
  return a(b);
}
function Hb() {
}
var Ib = false;
function Jb(a, b, c) {
  if (Ib) return a(b, c);
  Ib = true;
  try {
    return Gb(a, b, c);
  } finally {
    if (Ib = false, null !== zb || null !== Ab) Hb(), Fb();
  }
}
function Kb(a, b) {
  var c = a.stateNode;
  if (null === c) return null;
  var d = Db(c);
  if (null === d) return null;
  c = d[b];
  a: switch (b) {
    case "onClick":
    case "onClickCapture":
    case "onDoubleClick":
    case "onDoubleClickCapture":
    case "onMouseDown":
    case "onMouseDownCapture":
    case "onMouseMove":
    case "onMouseMoveCapture":
    case "onMouseUp":
    case "onMouseUpCapture":
    case "onMouseEnter":
      (d = !d.disabled) || (a = a.type, d = !("button" === a || "input" === a || "select" === a || "textarea" === a));
      a = !d;
      break a;
    default:
      a = false;
  }
  if (a) return null;
  if (c && "function" !== typeof c) throw Error(p(231, b, typeof c));
  return c;
}
var Lb = false;
if (ia) try {
  var Mb = {};
  Object.defineProperty(Mb, "passive", { get: function() {
    Lb = true;
  } });
  window.addEventListener("test", Mb, Mb);
  window.removeEventListener("test", Mb, Mb);
} catch (a) {
  Lb = false;
}
function Nb(a, b, c, d, e, f2, g, h, k2) {
  var l2 = Array.prototype.slice.call(arguments, 3);
  try {
    b.apply(c, l2);
  } catch (m2) {
    this.onError(m2);
  }
}
var Ob = false, Pb = null, Qb = false, Rb = null, Sb = { onError: function(a) {
  Ob = true;
  Pb = a;
} };
function Tb(a, b, c, d, e, f2, g, h, k2) {
  Ob = false;
  Pb = null;
  Nb.apply(Sb, arguments);
}
function Ub(a, b, c, d, e, f2, g, h, k2) {
  Tb.apply(this, arguments);
  if (Ob) {
    if (Ob) {
      var l2 = Pb;
      Ob = false;
      Pb = null;
    } else throw Error(p(198));
    Qb || (Qb = true, Rb = l2);
  }
}
function Vb(a) {
  var b = a, c = a;
  if (a.alternate) for (; b.return; ) b = b.return;
  else {
    a = b;
    do
      b = a, 0 !== (b.flags & 4098) && (c = b.return), a = b.return;
    while (a);
  }
  return 3 === b.tag ? c : null;
}
function Wb(a) {
  if (13 === a.tag) {
    var b = a.memoizedState;
    null === b && (a = a.alternate, null !== a && (b = a.memoizedState));
    if (null !== b) return b.dehydrated;
  }
  return null;
}
function Xb(a) {
  if (Vb(a) !== a) throw Error(p(188));
}
function Yb(a) {
  var b = a.alternate;
  if (!b) {
    b = Vb(a);
    if (null === b) throw Error(p(188));
    return b !== a ? null : a;
  }
  for (var c = a, d = b; ; ) {
    var e = c.return;
    if (null === e) break;
    var f2 = e.alternate;
    if (null === f2) {
      d = e.return;
      if (null !== d) {
        c = d;
        continue;
      }
      break;
    }
    if (e.child === f2.child) {
      for (f2 = e.child; f2; ) {
        if (f2 === c) return Xb(e), a;
        if (f2 === d) return Xb(e), b;
        f2 = f2.sibling;
      }
      throw Error(p(188));
    }
    if (c.return !== d.return) c = e, d = f2;
    else {
      for (var g = false, h = e.child; h; ) {
        if (h === c) {
          g = true;
          c = e;
          d = f2;
          break;
        }
        if (h === d) {
          g = true;
          d = e;
          c = f2;
          break;
        }
        h = h.sibling;
      }
      if (!g) {
        for (h = f2.child; h; ) {
          if (h === c) {
            g = true;
            c = f2;
            d = e;
            break;
          }
          if (h === d) {
            g = true;
            d = f2;
            c = e;
            break;
          }
          h = h.sibling;
        }
        if (!g) throw Error(p(189));
      }
    }
    if (c.alternate !== d) throw Error(p(190));
  }
  if (3 !== c.tag) throw Error(p(188));
  return c.stateNode.current === c ? a : b;
}
function Zb(a) {
  a = Yb(a);
  return null !== a ? $b(a) : null;
}
function $b(a) {
  if (5 === a.tag || 6 === a.tag) return a;
  for (a = a.child; null !== a; ) {
    var b = $b(a);
    if (null !== b) return b;
    a = a.sibling;
  }
  return null;
}
var ac = ca.unstable_scheduleCallback, bc = ca.unstable_cancelCallback, cc = ca.unstable_shouldYield, dc = ca.unstable_requestPaint, B = ca.unstable_now, ec = ca.unstable_getCurrentPriorityLevel, fc = ca.unstable_ImmediatePriority, gc = ca.unstable_UserBlockingPriority, hc = ca.unstable_NormalPriority, ic = ca.unstable_LowPriority, jc = ca.unstable_IdlePriority, kc = null, lc = null;
function mc(a) {
  if (lc && "function" === typeof lc.onCommitFiberRoot) try {
    lc.onCommitFiberRoot(kc, a, void 0, 128 === (a.current.flags & 128));
  } catch (b) {
  }
}
var oc = Math.clz32 ? Math.clz32 : nc, pc = Math.log, qc = Math.LN2;
function nc(a) {
  a >>>= 0;
  return 0 === a ? 32 : 31 - (pc(a) / qc | 0) | 0;
}
var rc = 64, sc = 4194304;
function tc(a) {
  switch (a & -a) {
    case 1:
      return 1;
    case 2:
      return 2;
    case 4:
      return 4;
    case 8:
      return 8;
    case 16:
      return 16;
    case 32:
      return 32;
    case 64:
    case 128:
    case 256:
    case 512:
    case 1024:
    case 2048:
    case 4096:
    case 8192:
    case 16384:
    case 32768:
    case 65536:
    case 131072:
    case 262144:
    case 524288:
    case 1048576:
    case 2097152:
      return a & 4194240;
    case 4194304:
    case 8388608:
    case 16777216:
    case 33554432:
    case 67108864:
      return a & 130023424;
    case 134217728:
      return 134217728;
    case 268435456:
      return 268435456;
    case 536870912:
      return 536870912;
    case 1073741824:
      return 1073741824;
    default:
      return a;
  }
}
function uc(a, b) {
  var c = a.pendingLanes;
  if (0 === c) return 0;
  var d = 0, e = a.suspendedLanes, f2 = a.pingedLanes, g = c & 268435455;
  if (0 !== g) {
    var h = g & ~e;
    0 !== h ? d = tc(h) : (f2 &= g, 0 !== f2 && (d = tc(f2)));
  } else g = c & ~e, 0 !== g ? d = tc(g) : 0 !== f2 && (d = tc(f2));
  if (0 === d) return 0;
  if (0 !== b && b !== d && 0 === (b & e) && (e = d & -d, f2 = b & -b, e >= f2 || 16 === e && 0 !== (f2 & 4194240))) return b;
  0 !== (d & 4) && (d |= c & 16);
  b = a.entangledLanes;
  if (0 !== b) for (a = a.entanglements, b &= d; 0 < b; ) c = 31 - oc(b), e = 1 << c, d |= a[c], b &= ~e;
  return d;
}
function vc(a, b) {
  switch (a) {
    case 1:
    case 2:
    case 4:
      return b + 250;
    case 8:
    case 16:
    case 32:
    case 64:
    case 128:
    case 256:
    case 512:
    case 1024:
    case 2048:
    case 4096:
    case 8192:
    case 16384:
    case 32768:
    case 65536:
    case 131072:
    case 262144:
    case 524288:
    case 1048576:
    case 2097152:
      return b + 5e3;
    case 4194304:
    case 8388608:
    case 16777216:
    case 33554432:
    case 67108864:
      return -1;
    case 134217728:
    case 268435456:
    case 536870912:
    case 1073741824:
      return -1;
    default:
      return -1;
  }
}
function wc(a, b) {
  for (var c = a.suspendedLanes, d = a.pingedLanes, e = a.expirationTimes, f2 = a.pendingLanes; 0 < f2; ) {
    var g = 31 - oc(f2), h = 1 << g, k2 = e[g];
    if (-1 === k2) {
      if (0 === (h & c) || 0 !== (h & d)) e[g] = vc(h, b);
    } else k2 <= b && (a.expiredLanes |= h);
    f2 &= ~h;
  }
}
function xc(a) {
  a = a.pendingLanes & -1073741825;
  return 0 !== a ? a : a & 1073741824 ? 1073741824 : 0;
}
function yc() {
  var a = rc;
  rc <<= 1;
  0 === (rc & 4194240) && (rc = 64);
  return a;
}
function zc(a) {
  for (var b = [], c = 0; 31 > c; c++) b.push(a);
  return b;
}
function Ac(a, b, c) {
  a.pendingLanes |= b;
  536870912 !== b && (a.suspendedLanes = 0, a.pingedLanes = 0);
  a = a.eventTimes;
  b = 31 - oc(b);
  a[b] = c;
}
function Bc(a, b) {
  var c = a.pendingLanes & ~b;
  a.pendingLanes = b;
  a.suspendedLanes = 0;
  a.pingedLanes = 0;
  a.expiredLanes &= b;
  a.mutableReadLanes &= b;
  a.entangledLanes &= b;
  b = a.entanglements;
  var d = a.eventTimes;
  for (a = a.expirationTimes; 0 < c; ) {
    var e = 31 - oc(c), f2 = 1 << e;
    b[e] = 0;
    d[e] = -1;
    a[e] = -1;
    c &= ~f2;
  }
}
function Cc(a, b) {
  var c = a.entangledLanes |= b;
  for (a = a.entanglements; c; ) {
    var d = 31 - oc(c), e = 1 << d;
    e & b | a[d] & b && (a[d] |= b);
    c &= ~e;
  }
}
var C = 0;
function Dc(a) {
  a &= -a;
  return 1 < a ? 4 < a ? 0 !== (a & 268435455) ? 16 : 536870912 : 4 : 1;
}
var Ec, Fc, Gc, Hc, Ic, Jc = false, Kc = [], Lc = null, Mc = null, Nc = null, Oc = /* @__PURE__ */ new Map(), Pc = /* @__PURE__ */ new Map(), Qc = [], Rc = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");
function Sc(a, b) {
  switch (a) {
    case "focusin":
    case "focusout":
      Lc = null;
      break;
    case "dragenter":
    case "dragleave":
      Mc = null;
      break;
    case "mouseover":
    case "mouseout":
      Nc = null;
      break;
    case "pointerover":
    case "pointerout":
      Oc.delete(b.pointerId);
      break;
    case "gotpointercapture":
    case "lostpointercapture":
      Pc.delete(b.pointerId);
  }
}
function Tc(a, b, c, d, e, f2) {
  if (null === a || a.nativeEvent !== f2) return a = { blockedOn: b, domEventName: c, eventSystemFlags: d, nativeEvent: f2, targetContainers: [e] }, null !== b && (b = Cb(b), null !== b && Fc(b)), a;
  a.eventSystemFlags |= d;
  b = a.targetContainers;
  null !== e && -1 === b.indexOf(e) && b.push(e);
  return a;
}
function Uc(a, b, c, d, e) {
  switch (b) {
    case "focusin":
      return Lc = Tc(Lc, a, b, c, d, e), true;
    case "dragenter":
      return Mc = Tc(Mc, a, b, c, d, e), true;
    case "mouseover":
      return Nc = Tc(Nc, a, b, c, d, e), true;
    case "pointerover":
      var f2 = e.pointerId;
      Oc.set(f2, Tc(Oc.get(f2) || null, a, b, c, d, e));
      return true;
    case "gotpointercapture":
      return f2 = e.pointerId, Pc.set(f2, Tc(Pc.get(f2) || null, a, b, c, d, e)), true;
  }
  return false;
}
function Vc(a) {
  var b = Wc(a.target);
  if (null !== b) {
    var c = Vb(b);
    if (null !== c) {
      if (b = c.tag, 13 === b) {
        if (b = Wb(c), null !== b) {
          a.blockedOn = b;
          Ic(a.priority, function() {
            Gc(c);
          });
          return;
        }
      } else if (3 === b && c.stateNode.current.memoizedState.isDehydrated) {
        a.blockedOn = 3 === c.tag ? c.stateNode.containerInfo : null;
        return;
      }
    }
  }
  a.blockedOn = null;
}
function Xc(a) {
  if (null !== a.blockedOn) return false;
  for (var b = a.targetContainers; 0 < b.length; ) {
    var c = Yc(a.domEventName, a.eventSystemFlags, b[0], a.nativeEvent);
    if (null === c) {
      c = a.nativeEvent;
      var d = new c.constructor(c.type, c);
      wb = d;
      c.target.dispatchEvent(d);
      wb = null;
    } else return b = Cb(c), null !== b && Fc(b), a.blockedOn = c, false;
    b.shift();
  }
  return true;
}
function Zc(a, b, c) {
  Xc(a) && c.delete(b);
}
function $c() {
  Jc = false;
  null !== Lc && Xc(Lc) && (Lc = null);
  null !== Mc && Xc(Mc) && (Mc = null);
  null !== Nc && Xc(Nc) && (Nc = null);
  Oc.forEach(Zc);
  Pc.forEach(Zc);
}
function ad(a, b) {
  a.blockedOn === b && (a.blockedOn = null, Jc || (Jc = true, ca.unstable_scheduleCallback(ca.unstable_NormalPriority, $c)));
}
function bd(a) {
  function b(b2) {
    return ad(b2, a);
  }
  if (0 < Kc.length) {
    ad(Kc[0], a);
    for (var c = 1; c < Kc.length; c++) {
      var d = Kc[c];
      d.blockedOn === a && (d.blockedOn = null);
    }
  }
  null !== Lc && ad(Lc, a);
  null !== Mc && ad(Mc, a);
  null !== Nc && ad(Nc, a);
  Oc.forEach(b);
  Pc.forEach(b);
  for (c = 0; c < Qc.length; c++) d = Qc[c], d.blockedOn === a && (d.blockedOn = null);
  for (; 0 < Qc.length && (c = Qc[0], null === c.blockedOn); ) Vc(c), null === c.blockedOn && Qc.shift();
}
var cd = ua.ReactCurrentBatchConfig, dd = true;
function ed(a, b, c, d) {
  var e = C, f2 = cd.transition;
  cd.transition = null;
  try {
    C = 1, fd(a, b, c, d);
  } finally {
    C = e, cd.transition = f2;
  }
}
function gd(a, b, c, d) {
  var e = C, f2 = cd.transition;
  cd.transition = null;
  try {
    C = 4, fd(a, b, c, d);
  } finally {
    C = e, cd.transition = f2;
  }
}
function fd(a, b, c, d) {
  if (dd) {
    var e = Yc(a, b, c, d);
    if (null === e) hd(a, b, d, id, c), Sc(a, d);
    else if (Uc(e, a, b, c, d)) d.stopPropagation();
    else if (Sc(a, d), b & 4 && -1 < Rc.indexOf(a)) {
      for (; null !== e; ) {
        var f2 = Cb(e);
        null !== f2 && Ec(f2);
        f2 = Yc(a, b, c, d);
        null === f2 && hd(a, b, d, id, c);
        if (f2 === e) break;
        e = f2;
      }
      null !== e && d.stopPropagation();
    } else hd(a, b, d, null, c);
  }
}
var id = null;
function Yc(a, b, c, d) {
  id = null;
  a = xb(d);
  a = Wc(a);
  if (null !== a) if (b = Vb(a), null === b) a = null;
  else if (c = b.tag, 13 === c) {
    a = Wb(b);
    if (null !== a) return a;
    a = null;
  } else if (3 === c) {
    if (b.stateNode.current.memoizedState.isDehydrated) return 3 === b.tag ? b.stateNode.containerInfo : null;
    a = null;
  } else b !== a && (a = null);
  id = a;
  return null;
}
function jd(a) {
  switch (a) {
    case "cancel":
    case "click":
    case "close":
    case "contextmenu":
    case "copy":
    case "cut":
    case "auxclick":
    case "dblclick":
    case "dragend":
    case "dragstart":
    case "drop":
    case "focusin":
    case "focusout":
    case "input":
    case "invalid":
    case "keydown":
    case "keypress":
    case "keyup":
    case "mousedown":
    case "mouseup":
    case "paste":
    case "pause":
    case "play":
    case "pointercancel":
    case "pointerdown":
    case "pointerup":
    case "ratechange":
    case "reset":
    case "resize":
    case "seeked":
    case "submit":
    case "touchcancel":
    case "touchend":
    case "touchstart":
    case "volumechange":
    case "change":
    case "selectionchange":
    case "textInput":
    case "compositionstart":
    case "compositionend":
    case "compositionupdate":
    case "beforeblur":
    case "afterblur":
    case "beforeinput":
    case "blur":
    case "fullscreenchange":
    case "focus":
    case "hashchange":
    case "popstate":
    case "select":
    case "selectstart":
      return 1;
    case "drag":
    case "dragenter":
    case "dragexit":
    case "dragleave":
    case "dragover":
    case "mousemove":
    case "mouseout":
    case "mouseover":
    case "pointermove":
    case "pointerout":
    case "pointerover":
    case "scroll":
    case "toggle":
    case "touchmove":
    case "wheel":
    case "mouseenter":
    case "mouseleave":
    case "pointerenter":
    case "pointerleave":
      return 4;
    case "message":
      switch (ec()) {
        case fc:
          return 1;
        case gc:
          return 4;
        case hc:
        case ic:
          return 16;
        case jc:
          return 536870912;
        default:
          return 16;
      }
    default:
      return 16;
  }
}
var kd = null, ld = null, md = null;
function nd() {
  if (md) return md;
  var a, b = ld, c = b.length, d, e = "value" in kd ? kd.value : kd.textContent, f2 = e.length;
  for (a = 0; a < c && b[a] === e[a]; a++) ;
  var g = c - a;
  for (d = 1; d <= g && b[c - d] === e[f2 - d]; d++) ;
  return md = e.slice(a, 1 < d ? 1 - d : void 0);
}
function od(a) {
  var b = a.keyCode;
  "charCode" in a ? (a = a.charCode, 0 === a && 13 === b && (a = 13)) : a = b;
  10 === a && (a = 13);
  return 32 <= a || 13 === a ? a : 0;
}
function pd() {
  return true;
}
function qd() {
  return false;
}
function rd(a) {
  function b(b2, d, e, f2, g) {
    this._reactName = b2;
    this._targetInst = e;
    this.type = d;
    this.nativeEvent = f2;
    this.target = g;
    this.currentTarget = null;
    for (var c in a) a.hasOwnProperty(c) && (b2 = a[c], this[c] = b2 ? b2(f2) : f2[c]);
    this.isDefaultPrevented = (null != f2.defaultPrevented ? f2.defaultPrevented : false === f2.returnValue) ? pd : qd;
    this.isPropagationStopped = qd;
    return this;
  }
  A(b.prototype, { preventDefault: function() {
    this.defaultPrevented = true;
    var a2 = this.nativeEvent;
    a2 && (a2.preventDefault ? a2.preventDefault() : "unknown" !== typeof a2.returnValue && (a2.returnValue = false), this.isDefaultPrevented = pd);
  }, stopPropagation: function() {
    var a2 = this.nativeEvent;
    a2 && (a2.stopPropagation ? a2.stopPropagation() : "unknown" !== typeof a2.cancelBubble && (a2.cancelBubble = true), this.isPropagationStopped = pd);
  }, persist: function() {
  }, isPersistent: pd });
  return b;
}
var sd = { eventPhase: 0, bubbles: 0, cancelable: 0, timeStamp: function(a) {
  return a.timeStamp || Date.now();
}, defaultPrevented: 0, isTrusted: 0 }, td = rd(sd), ud = A({}, sd, { view: 0, detail: 0 }), vd = rd(ud), wd, xd, yd, Ad = A({}, ud, { screenX: 0, screenY: 0, clientX: 0, clientY: 0, pageX: 0, pageY: 0, ctrlKey: 0, shiftKey: 0, altKey: 0, metaKey: 0, getModifierState: zd, button: 0, buttons: 0, relatedTarget: function(a) {
  return void 0 === a.relatedTarget ? a.fromElement === a.srcElement ? a.toElement : a.fromElement : a.relatedTarget;
}, movementX: function(a) {
  if ("movementX" in a) return a.movementX;
  a !== yd && (yd && "mousemove" === a.type ? (wd = a.screenX - yd.screenX, xd = a.screenY - yd.screenY) : xd = wd = 0, yd = a);
  return wd;
}, movementY: function(a) {
  return "movementY" in a ? a.movementY : xd;
} }), Bd = rd(Ad), Cd = A({}, Ad, { dataTransfer: 0 }), Dd = rd(Cd), Ed = A({}, ud, { relatedTarget: 0 }), Fd = rd(Ed), Gd = A({}, sd, { animationName: 0, elapsedTime: 0, pseudoElement: 0 }), Hd = rd(Gd), Id = A({}, sd, { clipboardData: function(a) {
  return "clipboardData" in a ? a.clipboardData : window.clipboardData;
} }), Jd = rd(Id), Kd = A({}, sd, { data: 0 }), Ld = rd(Kd), Md = {
  Esc: "Escape",
  Spacebar: " ",
  Left: "ArrowLeft",
  Up: "ArrowUp",
  Right: "ArrowRight",
  Down: "ArrowDown",
  Del: "Delete",
  Win: "OS",
  Menu: "ContextMenu",
  Apps: "ContextMenu",
  Scroll: "ScrollLock",
  MozPrintableKey: "Unidentified"
}, Nd = {
  8: "Backspace",
  9: "Tab",
  12: "Clear",
  13: "Enter",
  16: "Shift",
  17: "Control",
  18: "Alt",
  19: "Pause",
  20: "CapsLock",
  27: "Escape",
  32: " ",
  33: "PageUp",
  34: "PageDown",
  35: "End",
  36: "Home",
  37: "ArrowLeft",
  38: "ArrowUp",
  39: "ArrowRight",
  40: "ArrowDown",
  45: "Insert",
  46: "Delete",
  112: "F1",
  113: "F2",
  114: "F3",
  115: "F4",
  116: "F5",
  117: "F6",
  118: "F7",
  119: "F8",
  120: "F9",
  121: "F10",
  122: "F11",
  123: "F12",
  144: "NumLock",
  145: "ScrollLock",
  224: "Meta"
}, Od = { Alt: "altKey", Control: "ctrlKey", Meta: "metaKey", Shift: "shiftKey" };
function Pd(a) {
  var b = this.nativeEvent;
  return b.getModifierState ? b.getModifierState(a) : (a = Od[a]) ? !!b[a] : false;
}
function zd() {
  return Pd;
}
var Qd = A({}, ud, { key: function(a) {
  if (a.key) {
    var b = Md[a.key] || a.key;
    if ("Unidentified" !== b) return b;
  }
  return "keypress" === a.type ? (a = od(a), 13 === a ? "Enter" : String.fromCharCode(a)) : "keydown" === a.type || "keyup" === a.type ? Nd[a.keyCode] || "Unidentified" : "";
}, code: 0, location: 0, ctrlKey: 0, shiftKey: 0, altKey: 0, metaKey: 0, repeat: 0, locale: 0, getModifierState: zd, charCode: function(a) {
  return "keypress" === a.type ? od(a) : 0;
}, keyCode: function(a) {
  return "keydown" === a.type || "keyup" === a.type ? a.keyCode : 0;
}, which: function(a) {
  return "keypress" === a.type ? od(a) : "keydown" === a.type || "keyup" === a.type ? a.keyCode : 0;
} }), Rd = rd(Qd), Sd = A({}, Ad, { pointerId: 0, width: 0, height: 0, pressure: 0, tangentialPressure: 0, tiltX: 0, tiltY: 0, twist: 0, pointerType: 0, isPrimary: 0 }), Td = rd(Sd), Ud = A({}, ud, { touches: 0, targetTouches: 0, changedTouches: 0, altKey: 0, metaKey: 0, ctrlKey: 0, shiftKey: 0, getModifierState: zd }), Vd = rd(Ud), Wd = A({}, sd, { propertyName: 0, elapsedTime: 0, pseudoElement: 0 }), Xd = rd(Wd), Yd = A({}, Ad, {
  deltaX: function(a) {
    return "deltaX" in a ? a.deltaX : "wheelDeltaX" in a ? -a.wheelDeltaX : 0;
  },
  deltaY: function(a) {
    return "deltaY" in a ? a.deltaY : "wheelDeltaY" in a ? -a.wheelDeltaY : "wheelDelta" in a ? -a.wheelDelta : 0;
  },
  deltaZ: 0,
  deltaMode: 0
}), Zd = rd(Yd), $d = [9, 13, 27, 32], ae = ia && "CompositionEvent" in window, be = null;
ia && "documentMode" in document && (be = document.documentMode);
var ce = ia && "TextEvent" in window && !be, de = ia && (!ae || be && 8 < be && 11 >= be), ee = String.fromCharCode(32), fe = false;
function ge(a, b) {
  switch (a) {
    case "keyup":
      return -1 !== $d.indexOf(b.keyCode);
    case "keydown":
      return 229 !== b.keyCode;
    case "keypress":
    case "mousedown":
    case "focusout":
      return true;
    default:
      return false;
  }
}
function he(a) {
  a = a.detail;
  return "object" === typeof a && "data" in a ? a.data : null;
}
var ie = false;
function je(a, b) {
  switch (a) {
    case "compositionend":
      return he(b);
    case "keypress":
      if (32 !== b.which) return null;
      fe = true;
      return ee;
    case "textInput":
      return a = b.data, a === ee && fe ? null : a;
    default:
      return null;
  }
}
function ke(a, b) {
  if (ie) return "compositionend" === a || !ae && ge(a, b) ? (a = nd(), md = ld = kd = null, ie = false, a) : null;
  switch (a) {
    case "paste":
      return null;
    case "keypress":
      if (!(b.ctrlKey || b.altKey || b.metaKey) || b.ctrlKey && b.altKey) {
        if (b.char && 1 < b.char.length) return b.char;
        if (b.which) return String.fromCharCode(b.which);
      }
      return null;
    case "compositionend":
      return de && "ko" !== b.locale ? null : b.data;
    default:
      return null;
  }
}
var le = { color: true, date: true, datetime: true, "datetime-local": true, email: true, month: true, number: true, password: true, range: true, search: true, tel: true, text: true, time: true, url: true, week: true };
function me(a) {
  var b = a && a.nodeName && a.nodeName.toLowerCase();
  return "input" === b ? !!le[a.type] : "textarea" === b ? true : false;
}
function ne(a, b, c, d) {
  Eb(d);
  b = oe(b, "onChange");
  0 < b.length && (c = new td("onChange", "change", null, c, d), a.push({ event: c, listeners: b }));
}
var pe = null, qe = null;
function re(a) {
  se(a, 0);
}
function te(a) {
  var b = ue(a);
  if (Wa(b)) return a;
}
function ve(a, b) {
  if ("change" === a) return b;
}
var we = false;
if (ia) {
  var xe;
  if (ia) {
    var ye = "oninput" in document;
    if (!ye) {
      var ze = document.createElement("div");
      ze.setAttribute("oninput", "return;");
      ye = "function" === typeof ze.oninput;
    }
    xe = ye;
  } else xe = false;
  we = xe && (!document.documentMode || 9 < document.documentMode);
}
function Ae() {
  pe && (pe.detachEvent("onpropertychange", Be), qe = pe = null);
}
function Be(a) {
  if ("value" === a.propertyName && te(qe)) {
    var b = [];
    ne(b, qe, a, xb(a));
    Jb(re, b);
  }
}
function Ce(a, b, c) {
  "focusin" === a ? (Ae(), pe = b, qe = c, pe.attachEvent("onpropertychange", Be)) : "focusout" === a && Ae();
}
function De(a) {
  if ("selectionchange" === a || "keyup" === a || "keydown" === a) return te(qe);
}
function Ee(a, b) {
  if ("click" === a) return te(b);
}
function Fe(a, b) {
  if ("input" === a || "change" === a) return te(b);
}
function Ge(a, b) {
  return a === b && (0 !== a || 1 / a === 1 / b) || a !== a && b !== b;
}
var He = "function" === typeof Object.is ? Object.is : Ge;
function Ie(a, b) {
  if (He(a, b)) return true;
  if ("object" !== typeof a || null === a || "object" !== typeof b || null === b) return false;
  var c = Object.keys(a), d = Object.keys(b);
  if (c.length !== d.length) return false;
  for (d = 0; d < c.length; d++) {
    var e = c[d];
    if (!ja.call(b, e) || !He(a[e], b[e])) return false;
  }
  return true;
}
function Je(a) {
  for (; a && a.firstChild; ) a = a.firstChild;
  return a;
}
function Ke(a, b) {
  var c = Je(a);
  a = 0;
  for (var d; c; ) {
    if (3 === c.nodeType) {
      d = a + c.textContent.length;
      if (a <= b && d >= b) return { node: c, offset: b - a };
      a = d;
    }
    a: {
      for (; c; ) {
        if (c.nextSibling) {
          c = c.nextSibling;
          break a;
        }
        c = c.parentNode;
      }
      c = void 0;
    }
    c = Je(c);
  }
}
function Le(a, b) {
  return a && b ? a === b ? true : a && 3 === a.nodeType ? false : b && 3 === b.nodeType ? Le(a, b.parentNode) : "contains" in a ? a.contains(b) : a.compareDocumentPosition ? !!(a.compareDocumentPosition(b) & 16) : false : false;
}
function Me() {
  for (var a = window, b = Xa(); b instanceof a.HTMLIFrameElement; ) {
    try {
      var c = "string" === typeof b.contentWindow.location.href;
    } catch (d) {
      c = false;
    }
    if (c) a = b.contentWindow;
    else break;
    b = Xa(a.document);
  }
  return b;
}
function Ne(a) {
  var b = a && a.nodeName && a.nodeName.toLowerCase();
  return b && ("input" === b && ("text" === a.type || "search" === a.type || "tel" === a.type || "url" === a.type || "password" === a.type) || "textarea" === b || "true" === a.contentEditable);
}
function Oe(a) {
  var b = Me(), c = a.focusedElem, d = a.selectionRange;
  if (b !== c && c && c.ownerDocument && Le(c.ownerDocument.documentElement, c)) {
    if (null !== d && Ne(c)) {
      if (b = d.start, a = d.end, void 0 === a && (a = b), "selectionStart" in c) c.selectionStart = b, c.selectionEnd = Math.min(a, c.value.length);
      else if (a = (b = c.ownerDocument || document) && b.defaultView || window, a.getSelection) {
        a = a.getSelection();
        var e = c.textContent.length, f2 = Math.min(d.start, e);
        d = void 0 === d.end ? f2 : Math.min(d.end, e);
        !a.extend && f2 > d && (e = d, d = f2, f2 = e);
        e = Ke(c, f2);
        var g = Ke(
          c,
          d
        );
        e && g && (1 !== a.rangeCount || a.anchorNode !== e.node || a.anchorOffset !== e.offset || a.focusNode !== g.node || a.focusOffset !== g.offset) && (b = b.createRange(), b.setStart(e.node, e.offset), a.removeAllRanges(), f2 > d ? (a.addRange(b), a.extend(g.node, g.offset)) : (b.setEnd(g.node, g.offset), a.addRange(b)));
      }
    }
    b = [];
    for (a = c; a = a.parentNode; ) 1 === a.nodeType && b.push({ element: a, left: a.scrollLeft, top: a.scrollTop });
    "function" === typeof c.focus && c.focus();
    for (c = 0; c < b.length; c++) a = b[c], a.element.scrollLeft = a.left, a.element.scrollTop = a.top;
  }
}
var Pe = ia && "documentMode" in document && 11 >= document.documentMode, Qe = null, Re = null, Se = null, Te = false;
function Ue(a, b, c) {
  var d = c.window === c ? c.document : 9 === c.nodeType ? c : c.ownerDocument;
  Te || null == Qe || Qe !== Xa(d) || (d = Qe, "selectionStart" in d && Ne(d) ? d = { start: d.selectionStart, end: d.selectionEnd } : (d = (d.ownerDocument && d.ownerDocument.defaultView || window).getSelection(), d = { anchorNode: d.anchorNode, anchorOffset: d.anchorOffset, focusNode: d.focusNode, focusOffset: d.focusOffset }), Se && Ie(Se, d) || (Se = d, d = oe(Re, "onSelect"), 0 < d.length && (b = new td("onSelect", "select", null, b, c), a.push({ event: b, listeners: d }), b.target = Qe)));
}
function Ve(a, b) {
  var c = {};
  c[a.toLowerCase()] = b.toLowerCase();
  c["Webkit" + a] = "webkit" + b;
  c["Moz" + a] = "moz" + b;
  return c;
}
var We = { animationend: Ve("Animation", "AnimationEnd"), animationiteration: Ve("Animation", "AnimationIteration"), animationstart: Ve("Animation", "AnimationStart"), transitionend: Ve("Transition", "TransitionEnd") }, Xe = {}, Ye = {};
ia && (Ye = document.createElement("div").style, "AnimationEvent" in window || (delete We.animationend.animation, delete We.animationiteration.animation, delete We.animationstart.animation), "TransitionEvent" in window || delete We.transitionend.transition);
function Ze(a) {
  if (Xe[a]) return Xe[a];
  if (!We[a]) return a;
  var b = We[a], c;
  for (c in b) if (b.hasOwnProperty(c) && c in Ye) return Xe[a] = b[c];
  return a;
}
var $e = Ze("animationend"), af = Ze("animationiteration"), bf = Ze("animationstart"), cf = Ze("transitionend"), df = /* @__PURE__ */ new Map(), ef = "abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
function ff(a, b) {
  df.set(a, b);
  fa(b, [a]);
}
for (var gf = 0; gf < ef.length; gf++) {
  var hf = ef[gf], jf = hf.toLowerCase(), kf = hf[0].toUpperCase() + hf.slice(1);
  ff(jf, "on" + kf);
}
ff($e, "onAnimationEnd");
ff(af, "onAnimationIteration");
ff(bf, "onAnimationStart");
ff("dblclick", "onDoubleClick");
ff("focusin", "onFocus");
ff("focusout", "onBlur");
ff(cf, "onTransitionEnd");
ha("onMouseEnter", ["mouseout", "mouseover"]);
ha("onMouseLeave", ["mouseout", "mouseover"]);
ha("onPointerEnter", ["pointerout", "pointerover"]);
ha("onPointerLeave", ["pointerout", "pointerover"]);
fa("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" "));
fa("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));
fa("onBeforeInput", ["compositionend", "keypress", "textInput", "paste"]);
fa("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" "));
fa("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" "));
fa("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
var lf = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "), mf = new Set("cancel close invalid load scroll toggle".split(" ").concat(lf));
function nf(a, b, c) {
  var d = a.type || "unknown-event";
  a.currentTarget = c;
  Ub(d, b, void 0, a);
  a.currentTarget = null;
}
function se(a, b) {
  b = 0 !== (b & 4);
  for (var c = 0; c < a.length; c++) {
    var d = a[c], e = d.event;
    d = d.listeners;
    a: {
      var f2 = void 0;
      if (b) for (var g = d.length - 1; 0 <= g; g--) {
        var h = d[g], k2 = h.instance, l2 = h.currentTarget;
        h = h.listener;
        if (k2 !== f2 && e.isPropagationStopped()) break a;
        nf(e, h, l2);
        f2 = k2;
      }
      else for (g = 0; g < d.length; g++) {
        h = d[g];
        k2 = h.instance;
        l2 = h.currentTarget;
        h = h.listener;
        if (k2 !== f2 && e.isPropagationStopped()) break a;
        nf(e, h, l2);
        f2 = k2;
      }
    }
  }
  if (Qb) throw a = Rb, Qb = false, Rb = null, a;
}
function D(a, b) {
  var c = b[of];
  void 0 === c && (c = b[of] = /* @__PURE__ */ new Set());
  var d = a + "__bubble";
  c.has(d) || (pf(b, a, 2, false), c.add(d));
}
function qf(a, b, c) {
  var d = 0;
  b && (d |= 4);
  pf(c, a, d, b);
}
var rf = "_reactListening" + Math.random().toString(36).slice(2);
function sf(a) {
  if (!a[rf]) {
    a[rf] = true;
    da.forEach(function(b2) {
      "selectionchange" !== b2 && (mf.has(b2) || qf(b2, false, a), qf(b2, true, a));
    });
    var b = 9 === a.nodeType ? a : a.ownerDocument;
    null === b || b[rf] || (b[rf] = true, qf("selectionchange", false, b));
  }
}
function pf(a, b, c, d) {
  switch (jd(b)) {
    case 1:
      var e = ed;
      break;
    case 4:
      e = gd;
      break;
    default:
      e = fd;
  }
  c = e.bind(null, b, c, a);
  e = void 0;
  !Lb || "touchstart" !== b && "touchmove" !== b && "wheel" !== b || (e = true);
  d ? void 0 !== e ? a.addEventListener(b, c, { capture: true, passive: e }) : a.addEventListener(b, c, true) : void 0 !== e ? a.addEventListener(b, c, { passive: e }) : a.addEventListener(b, c, false);
}
function hd(a, b, c, d, e) {
  var f2 = d;
  if (0 === (b & 1) && 0 === (b & 2) && null !== d) a: for (; ; ) {
    if (null === d) return;
    var g = d.tag;
    if (3 === g || 4 === g) {
      var h = d.stateNode.containerInfo;
      if (h === e || 8 === h.nodeType && h.parentNode === e) break;
      if (4 === g) for (g = d.return; null !== g; ) {
        var k2 = g.tag;
        if (3 === k2 || 4 === k2) {
          if (k2 = g.stateNode.containerInfo, k2 === e || 8 === k2.nodeType && k2.parentNode === e) return;
        }
        g = g.return;
      }
      for (; null !== h; ) {
        g = Wc(h);
        if (null === g) return;
        k2 = g.tag;
        if (5 === k2 || 6 === k2) {
          d = f2 = g;
          continue a;
        }
        h = h.parentNode;
      }
    }
    d = d.return;
  }
  Jb(function() {
    var d2 = f2, e2 = xb(c), g2 = [];
    a: {
      var h2 = df.get(a);
      if (void 0 !== h2) {
        var k3 = td, n2 = a;
        switch (a) {
          case "keypress":
            if (0 === od(c)) break a;
          case "keydown":
          case "keyup":
            k3 = Rd;
            break;
          case "focusin":
            n2 = "focus";
            k3 = Fd;
            break;
          case "focusout":
            n2 = "blur";
            k3 = Fd;
            break;
          case "beforeblur":
          case "afterblur":
            k3 = Fd;
            break;
          case "click":
            if (2 === c.button) break a;
          case "auxclick":
          case "dblclick":
          case "mousedown":
          case "mousemove":
          case "mouseup":
          case "mouseout":
          case "mouseover":
          case "contextmenu":
            k3 = Bd;
            break;
          case "drag":
          case "dragend":
          case "dragenter":
          case "dragexit":
          case "dragleave":
          case "dragover":
          case "dragstart":
          case "drop":
            k3 = Dd;
            break;
          case "touchcancel":
          case "touchend":
          case "touchmove":
          case "touchstart":
            k3 = Vd;
            break;
          case $e:
          case af:
          case bf:
            k3 = Hd;
            break;
          case cf:
            k3 = Xd;
            break;
          case "scroll":
            k3 = vd;
            break;
          case "wheel":
            k3 = Zd;
            break;
          case "copy":
          case "cut":
          case "paste":
            k3 = Jd;
            break;
          case "gotpointercapture":
          case "lostpointercapture":
          case "pointercancel":
          case "pointerdown":
          case "pointermove":
          case "pointerout":
          case "pointerover":
          case "pointerup":
            k3 = Td;
        }
        var t2 = 0 !== (b & 4), J2 = !t2 && "scroll" === a, x2 = t2 ? null !== h2 ? h2 + "Capture" : null : h2;
        t2 = [];
        for (var w2 = d2, u2; null !== w2; ) {
          u2 = w2;
          var F2 = u2.stateNode;
          5 === u2.tag && null !== F2 && (u2 = F2, null !== x2 && (F2 = Kb(w2, x2), null != F2 && t2.push(tf(w2, F2, u2))));
          if (J2) break;
          w2 = w2.return;
        }
        0 < t2.length && (h2 = new k3(h2, n2, null, c, e2), g2.push({ event: h2, listeners: t2 }));
      }
    }
    if (0 === (b & 7)) {
      a: {
        h2 = "mouseover" === a || "pointerover" === a;
        k3 = "mouseout" === a || "pointerout" === a;
        if (h2 && c !== wb && (n2 = c.relatedTarget || c.fromElement) && (Wc(n2) || n2[uf])) break a;
        if (k3 || h2) {
          h2 = e2.window === e2 ? e2 : (h2 = e2.ownerDocument) ? h2.defaultView || h2.parentWindow : window;
          if (k3) {
            if (n2 = c.relatedTarget || c.toElement, k3 = d2, n2 = n2 ? Wc(n2) : null, null !== n2 && (J2 = Vb(n2), n2 !== J2 || 5 !== n2.tag && 6 !== n2.tag)) n2 = null;
          } else k3 = null, n2 = d2;
          if (k3 !== n2) {
            t2 = Bd;
            F2 = "onMouseLeave";
            x2 = "onMouseEnter";
            w2 = "mouse";
            if ("pointerout" === a || "pointerover" === a) t2 = Td, F2 = "onPointerLeave", x2 = "onPointerEnter", w2 = "pointer";
            J2 = null == k3 ? h2 : ue(k3);
            u2 = null == n2 ? h2 : ue(n2);
            h2 = new t2(F2, w2 + "leave", k3, c, e2);
            h2.target = J2;
            h2.relatedTarget = u2;
            F2 = null;
            Wc(e2) === d2 && (t2 = new t2(x2, w2 + "enter", n2, c, e2), t2.target = u2, t2.relatedTarget = J2, F2 = t2);
            J2 = F2;
            if (k3 && n2) b: {
              t2 = k3;
              x2 = n2;
              w2 = 0;
              for (u2 = t2; u2; u2 = vf(u2)) w2++;
              u2 = 0;
              for (F2 = x2; F2; F2 = vf(F2)) u2++;
              for (; 0 < w2 - u2; ) t2 = vf(t2), w2--;
              for (; 0 < u2 - w2; ) x2 = vf(x2), u2--;
              for (; w2--; ) {
                if (t2 === x2 || null !== x2 && t2 === x2.alternate) break b;
                t2 = vf(t2);
                x2 = vf(x2);
              }
              t2 = null;
            }
            else t2 = null;
            null !== k3 && wf(g2, h2, k3, t2, false);
            null !== n2 && null !== J2 && wf(g2, J2, n2, t2, true);
          }
        }
      }
      a: {
        h2 = d2 ? ue(d2) : window;
        k3 = h2.nodeName && h2.nodeName.toLowerCase();
        if ("select" === k3 || "input" === k3 && "file" === h2.type) var na = ve;
        else if (me(h2)) if (we) na = Fe;
        else {
          na = De;
          var xa = Ce;
        }
        else (k3 = h2.nodeName) && "input" === k3.toLowerCase() && ("checkbox" === h2.type || "radio" === h2.type) && (na = Ee);
        if (na && (na = na(a, d2))) {
          ne(g2, na, c, e2);
          break a;
        }
        xa && xa(a, h2, d2);
        "focusout" === a && (xa = h2._wrapperState) && xa.controlled && "number" === h2.type && cb(h2, "number", h2.value);
      }
      xa = d2 ? ue(d2) : window;
      switch (a) {
        case "focusin":
          if (me(xa) || "true" === xa.contentEditable) Qe = xa, Re = d2, Se = null;
          break;
        case "focusout":
          Se = Re = Qe = null;
          break;
        case "mousedown":
          Te = true;
          break;
        case "contextmenu":
        case "mouseup":
        case "dragend":
          Te = false;
          Ue(g2, c, e2);
          break;
        case "selectionchange":
          if (Pe) break;
        case "keydown":
        case "keyup":
          Ue(g2, c, e2);
      }
      var $a;
      if (ae) b: {
        switch (a) {
          case "compositionstart":
            var ba = "onCompositionStart";
            break b;
          case "compositionend":
            ba = "onCompositionEnd";
            break b;
          case "compositionupdate":
            ba = "onCompositionUpdate";
            break b;
        }
        ba = void 0;
      }
      else ie ? ge(a, c) && (ba = "onCompositionEnd") : "keydown" === a && 229 === c.keyCode && (ba = "onCompositionStart");
      ba && (de && "ko" !== c.locale && (ie || "onCompositionStart" !== ba ? "onCompositionEnd" === ba && ie && ($a = nd()) : (kd = e2, ld = "value" in kd ? kd.value : kd.textContent, ie = true)), xa = oe(d2, ba), 0 < xa.length && (ba = new Ld(ba, a, null, c, e2), g2.push({ event: ba, listeners: xa }), $a ? ba.data = $a : ($a = he(c), null !== $a && (ba.data = $a))));
      if ($a = ce ? je(a, c) : ke(a, c)) d2 = oe(d2, "onBeforeInput"), 0 < d2.length && (e2 = new Ld("onBeforeInput", "beforeinput", null, c, e2), g2.push({ event: e2, listeners: d2 }), e2.data = $a);
    }
    se(g2, b);
  });
}
function tf(a, b, c) {
  return { instance: a, listener: b, currentTarget: c };
}
function oe(a, b) {
  for (var c = b + "Capture", d = []; null !== a; ) {
    var e = a, f2 = e.stateNode;
    5 === e.tag && null !== f2 && (e = f2, f2 = Kb(a, c), null != f2 && d.unshift(tf(a, f2, e)), f2 = Kb(a, b), null != f2 && d.push(tf(a, f2, e)));
    a = a.return;
  }
  return d;
}
function vf(a) {
  if (null === a) return null;
  do
    a = a.return;
  while (a && 5 !== a.tag);
  return a ? a : null;
}
function wf(a, b, c, d, e) {
  for (var f2 = b._reactName, g = []; null !== c && c !== d; ) {
    var h = c, k2 = h.alternate, l2 = h.stateNode;
    if (null !== k2 && k2 === d) break;
    5 === h.tag && null !== l2 && (h = l2, e ? (k2 = Kb(c, f2), null != k2 && g.unshift(tf(c, k2, h))) : e || (k2 = Kb(c, f2), null != k2 && g.push(tf(c, k2, h))));
    c = c.return;
  }
  0 !== g.length && a.push({ event: b, listeners: g });
}
var xf = /\r\n?/g, yf = /\u0000|\uFFFD/g;
function zf(a) {
  return ("string" === typeof a ? a : "" + a).replace(xf, "\n").replace(yf, "");
}
function Af(a, b, c) {
  b = zf(b);
  if (zf(a) !== b && c) throw Error(p(425));
}
function Bf() {
}
var Cf = null, Df = null;
function Ef(a, b) {
  return "textarea" === a || "noscript" === a || "string" === typeof b.children || "number" === typeof b.children || "object" === typeof b.dangerouslySetInnerHTML && null !== b.dangerouslySetInnerHTML && null != b.dangerouslySetInnerHTML.__html;
}
var Ff = "function" === typeof setTimeout ? setTimeout : void 0, Gf = "function" === typeof clearTimeout ? clearTimeout : void 0, Hf = "function" === typeof Promise ? Promise : void 0, Jf = "function" === typeof queueMicrotask ? queueMicrotask : "undefined" !== typeof Hf ? function(a) {
  return Hf.resolve(null).then(a).catch(If);
} : Ff;
function If(a) {
  setTimeout(function() {
    throw a;
  });
}
function Kf(a, b) {
  var c = b, d = 0;
  do {
    var e = c.nextSibling;
    a.removeChild(c);
    if (e && 8 === e.nodeType) if (c = e.data, "/$" === c) {
      if (0 === d) {
        a.removeChild(e);
        bd(b);
        return;
      }
      d--;
    } else "$" !== c && "$?" !== c && "$!" !== c || d++;
    c = e;
  } while (c);
  bd(b);
}
function Lf(a) {
  for (; null != a; a = a.nextSibling) {
    var b = a.nodeType;
    if (1 === b || 3 === b) break;
    if (8 === b) {
      b = a.data;
      if ("$" === b || "$!" === b || "$?" === b) break;
      if ("/$" === b) return null;
    }
  }
  return a;
}
function Mf(a) {
  a = a.previousSibling;
  for (var b = 0; a; ) {
    if (8 === a.nodeType) {
      var c = a.data;
      if ("$" === c || "$!" === c || "$?" === c) {
        if (0 === b) return a;
        b--;
      } else "/$" === c && b++;
    }
    a = a.previousSibling;
  }
  return null;
}
var Nf = Math.random().toString(36).slice(2), Of = "__reactFiber$" + Nf, Pf = "__reactProps$" + Nf, uf = "__reactContainer$" + Nf, of = "__reactEvents$" + Nf, Qf = "__reactListeners$" + Nf, Rf = "__reactHandles$" + Nf;
function Wc(a) {
  var b = a[Of];
  if (b) return b;
  for (var c = a.parentNode; c; ) {
    if (b = c[uf] || c[Of]) {
      c = b.alternate;
      if (null !== b.child || null !== c && null !== c.child) for (a = Mf(a); null !== a; ) {
        if (c = a[Of]) return c;
        a = Mf(a);
      }
      return b;
    }
    a = c;
    c = a.parentNode;
  }
  return null;
}
function Cb(a) {
  a = a[Of] || a[uf];
  return !a || 5 !== a.tag && 6 !== a.tag && 13 !== a.tag && 3 !== a.tag ? null : a;
}
function ue(a) {
  if (5 === a.tag || 6 === a.tag) return a.stateNode;
  throw Error(p(33));
}
function Db(a) {
  return a[Pf] || null;
}
var Sf = [], Tf = -1;
function Uf(a) {
  return { current: a };
}
function E(a) {
  0 > Tf || (a.current = Sf[Tf], Sf[Tf] = null, Tf--);
}
function G(a, b) {
  Tf++;
  Sf[Tf] = a.current;
  a.current = b;
}
var Vf = {}, H = Uf(Vf), Wf = Uf(false), Xf = Vf;
function Yf(a, b) {
  var c = a.type.contextTypes;
  if (!c) return Vf;
  var d = a.stateNode;
  if (d && d.__reactInternalMemoizedUnmaskedChildContext === b) return d.__reactInternalMemoizedMaskedChildContext;
  var e = {}, f2;
  for (f2 in c) e[f2] = b[f2];
  d && (a = a.stateNode, a.__reactInternalMemoizedUnmaskedChildContext = b, a.__reactInternalMemoizedMaskedChildContext = e);
  return e;
}
function Zf(a) {
  a = a.childContextTypes;
  return null !== a && void 0 !== a;
}
function $f() {
  E(Wf);
  E(H);
}
function ag(a, b, c) {
  if (H.current !== Vf) throw Error(p(168));
  G(H, b);
  G(Wf, c);
}
function bg(a, b, c) {
  var d = a.stateNode;
  b = b.childContextTypes;
  if ("function" !== typeof d.getChildContext) return c;
  d = d.getChildContext();
  for (var e in d) if (!(e in b)) throw Error(p(108, Ra(a) || "Unknown", e));
  return A({}, c, d);
}
function cg(a) {
  a = (a = a.stateNode) && a.__reactInternalMemoizedMergedChildContext || Vf;
  Xf = H.current;
  G(H, a);
  G(Wf, Wf.current);
  return true;
}
function dg(a, b, c) {
  var d = a.stateNode;
  if (!d) throw Error(p(169));
  c ? (a = bg(a, b, Xf), d.__reactInternalMemoizedMergedChildContext = a, E(Wf), E(H), G(H, a)) : E(Wf);
  G(Wf, c);
}
var eg = null, fg = false, gg = false;
function hg(a) {
  null === eg ? eg = [a] : eg.push(a);
}
function ig(a) {
  fg = true;
  hg(a);
}
function jg() {
  if (!gg && null !== eg) {
    gg = true;
    var a = 0, b = C;
    try {
      var c = eg;
      for (C = 1; a < c.length; a++) {
        var d = c[a];
        do
          d = d(true);
        while (null !== d);
      }
      eg = null;
      fg = false;
    } catch (e) {
      throw null !== eg && (eg = eg.slice(a + 1)), ac(fc, jg), e;
    } finally {
      C = b, gg = false;
    }
  }
  return null;
}
var kg = [], lg = 0, mg = null, ng = 0, og = [], pg = 0, qg = null, rg = 1, sg = "";
function tg(a, b) {
  kg[lg++] = ng;
  kg[lg++] = mg;
  mg = a;
  ng = b;
}
function ug(a, b, c) {
  og[pg++] = rg;
  og[pg++] = sg;
  og[pg++] = qg;
  qg = a;
  var d = rg;
  a = sg;
  var e = 32 - oc(d) - 1;
  d &= ~(1 << e);
  c += 1;
  var f2 = 32 - oc(b) + e;
  if (30 < f2) {
    var g = e - e % 5;
    f2 = (d & (1 << g) - 1).toString(32);
    d >>= g;
    e -= g;
    rg = 1 << 32 - oc(b) + e | c << e | d;
    sg = f2 + a;
  } else rg = 1 << f2 | c << e | d, sg = a;
}
function vg(a) {
  null !== a.return && (tg(a, 1), ug(a, 1, 0));
}
function wg(a) {
  for (; a === mg; ) mg = kg[--lg], kg[lg] = null, ng = kg[--lg], kg[lg] = null;
  for (; a === qg; ) qg = og[--pg], og[pg] = null, sg = og[--pg], og[pg] = null, rg = og[--pg], og[pg] = null;
}
var xg = null, yg = null, I = false, zg = null;
function Ag(a, b) {
  var c = Bg(5, null, null, 0);
  c.elementType = "DELETED";
  c.stateNode = b;
  c.return = a;
  b = a.deletions;
  null === b ? (a.deletions = [c], a.flags |= 16) : b.push(c);
}
function Cg(a, b) {
  switch (a.tag) {
    case 5:
      var c = a.type;
      b = 1 !== b.nodeType || c.toLowerCase() !== b.nodeName.toLowerCase() ? null : b;
      return null !== b ? (a.stateNode = b, xg = a, yg = Lf(b.firstChild), true) : false;
    case 6:
      return b = "" === a.pendingProps || 3 !== b.nodeType ? null : b, null !== b ? (a.stateNode = b, xg = a, yg = null, true) : false;
    case 13:
      return b = 8 !== b.nodeType ? null : b, null !== b ? (c = null !== qg ? { id: rg, overflow: sg } : null, a.memoizedState = { dehydrated: b, treeContext: c, retryLane: 1073741824 }, c = Bg(18, null, null, 0), c.stateNode = b, c.return = a, a.child = c, xg = a, yg = null, true) : false;
    default:
      return false;
  }
}
function Dg(a) {
  return 0 !== (a.mode & 1) && 0 === (a.flags & 128);
}
function Eg(a) {
  if (I) {
    var b = yg;
    if (b) {
      var c = b;
      if (!Cg(a, b)) {
        if (Dg(a)) throw Error(p(418));
        b = Lf(c.nextSibling);
        var d = xg;
        b && Cg(a, b) ? Ag(d, c) : (a.flags = a.flags & -4097 | 2, I = false, xg = a);
      }
    } else {
      if (Dg(a)) throw Error(p(418));
      a.flags = a.flags & -4097 | 2;
      I = false;
      xg = a;
    }
  }
}
function Fg(a) {
  for (a = a.return; null !== a && 5 !== a.tag && 3 !== a.tag && 13 !== a.tag; ) a = a.return;
  xg = a;
}
function Gg(a) {
  if (a !== xg) return false;
  if (!I) return Fg(a), I = true, false;
  var b;
  (b = 3 !== a.tag) && !(b = 5 !== a.tag) && (b = a.type, b = "head" !== b && "body" !== b && !Ef(a.type, a.memoizedProps));
  if (b && (b = yg)) {
    if (Dg(a)) throw Hg(), Error(p(418));
    for (; b; ) Ag(a, b), b = Lf(b.nextSibling);
  }
  Fg(a);
  if (13 === a.tag) {
    a = a.memoizedState;
    a = null !== a ? a.dehydrated : null;
    if (!a) throw Error(p(317));
    a: {
      a = a.nextSibling;
      for (b = 0; a; ) {
        if (8 === a.nodeType) {
          var c = a.data;
          if ("/$" === c) {
            if (0 === b) {
              yg = Lf(a.nextSibling);
              break a;
            }
            b--;
          } else "$" !== c && "$!" !== c && "$?" !== c || b++;
        }
        a = a.nextSibling;
      }
      yg = null;
    }
  } else yg = xg ? Lf(a.stateNode.nextSibling) : null;
  return true;
}
function Hg() {
  for (var a = yg; a; ) a = Lf(a.nextSibling);
}
function Ig() {
  yg = xg = null;
  I = false;
}
function Jg(a) {
  null === zg ? zg = [a] : zg.push(a);
}
var Kg = ua.ReactCurrentBatchConfig;
function Lg(a, b, c) {
  a = c.ref;
  if (null !== a && "function" !== typeof a && "object" !== typeof a) {
    if (c._owner) {
      c = c._owner;
      if (c) {
        if (1 !== c.tag) throw Error(p(309));
        var d = c.stateNode;
      }
      if (!d) throw Error(p(147, a));
      var e = d, f2 = "" + a;
      if (null !== b && null !== b.ref && "function" === typeof b.ref && b.ref._stringRef === f2) return b.ref;
      b = function(a2) {
        var b2 = e.refs;
        null === a2 ? delete b2[f2] : b2[f2] = a2;
      };
      b._stringRef = f2;
      return b;
    }
    if ("string" !== typeof a) throw Error(p(284));
    if (!c._owner) throw Error(p(290, a));
  }
  return a;
}
function Mg(a, b) {
  a = Object.prototype.toString.call(b);
  throw Error(p(31, "[object Object]" === a ? "object with keys {" + Object.keys(b).join(", ") + "}" : a));
}
function Ng(a) {
  var b = a._init;
  return b(a._payload);
}
function Og(a) {
  function b(b2, c2) {
    if (a) {
      var d2 = b2.deletions;
      null === d2 ? (b2.deletions = [c2], b2.flags |= 16) : d2.push(c2);
    }
  }
  function c(c2, d2) {
    if (!a) return null;
    for (; null !== d2; ) b(c2, d2), d2 = d2.sibling;
    return null;
  }
  function d(a2, b2) {
    for (a2 = /* @__PURE__ */ new Map(); null !== b2; ) null !== b2.key ? a2.set(b2.key, b2) : a2.set(b2.index, b2), b2 = b2.sibling;
    return a2;
  }
  function e(a2, b2) {
    a2 = Pg(a2, b2);
    a2.index = 0;
    a2.sibling = null;
    return a2;
  }
  function f2(b2, c2, d2) {
    b2.index = d2;
    if (!a) return b2.flags |= 1048576, c2;
    d2 = b2.alternate;
    if (null !== d2) return d2 = d2.index, d2 < c2 ? (b2.flags |= 2, c2) : d2;
    b2.flags |= 2;
    return c2;
  }
  function g(b2) {
    a && null === b2.alternate && (b2.flags |= 2);
    return b2;
  }
  function h(a2, b2, c2, d2) {
    if (null === b2 || 6 !== b2.tag) return b2 = Qg(c2, a2.mode, d2), b2.return = a2, b2;
    b2 = e(b2, c2);
    b2.return = a2;
    return b2;
  }
  function k2(a2, b2, c2, d2) {
    var f3 = c2.type;
    if (f3 === ya) return m2(a2, b2, c2.props.children, d2, c2.key);
    if (null !== b2 && (b2.elementType === f3 || "object" === typeof f3 && null !== f3 && f3.$$typeof === Ha && Ng(f3) === b2.type)) return d2 = e(b2, c2.props), d2.ref = Lg(a2, b2, c2), d2.return = a2, d2;
    d2 = Rg(c2.type, c2.key, c2.props, null, a2.mode, d2);
    d2.ref = Lg(a2, b2, c2);
    d2.return = a2;
    return d2;
  }
  function l2(a2, b2, c2, d2) {
    if (null === b2 || 4 !== b2.tag || b2.stateNode.containerInfo !== c2.containerInfo || b2.stateNode.implementation !== c2.implementation) return b2 = Sg(c2, a2.mode, d2), b2.return = a2, b2;
    b2 = e(b2, c2.children || []);
    b2.return = a2;
    return b2;
  }
  function m2(a2, b2, c2, d2, f3) {
    if (null === b2 || 7 !== b2.tag) return b2 = Tg(c2, a2.mode, d2, f3), b2.return = a2, b2;
    b2 = e(b2, c2);
    b2.return = a2;
    return b2;
  }
  function q2(a2, b2, c2) {
    if ("string" === typeof b2 && "" !== b2 || "number" === typeof b2) return b2 = Qg("" + b2, a2.mode, c2), b2.return = a2, b2;
    if ("object" === typeof b2 && null !== b2) {
      switch (b2.$$typeof) {
        case va:
          return c2 = Rg(b2.type, b2.key, b2.props, null, a2.mode, c2), c2.ref = Lg(a2, null, b2), c2.return = a2, c2;
        case wa:
          return b2 = Sg(b2, a2.mode, c2), b2.return = a2, b2;
        case Ha:
          var d2 = b2._init;
          return q2(a2, d2(b2._payload), c2);
      }
      if (eb(b2) || Ka(b2)) return b2 = Tg(b2, a2.mode, c2, null), b2.return = a2, b2;
      Mg(a2, b2);
    }
    return null;
  }
  function r2(a2, b2, c2, d2) {
    var e2 = null !== b2 ? b2.key : null;
    if ("string" === typeof c2 && "" !== c2 || "number" === typeof c2) return null !== e2 ? null : h(a2, b2, "" + c2, d2);
    if ("object" === typeof c2 && null !== c2) {
      switch (c2.$$typeof) {
        case va:
          return c2.key === e2 ? k2(a2, b2, c2, d2) : null;
        case wa:
          return c2.key === e2 ? l2(a2, b2, c2, d2) : null;
        case Ha:
          return e2 = c2._init, r2(
            a2,
            b2,
            e2(c2._payload),
            d2
          );
      }
      if (eb(c2) || Ka(c2)) return null !== e2 ? null : m2(a2, b2, c2, d2, null);
      Mg(a2, c2);
    }
    return null;
  }
  function y2(a2, b2, c2, d2, e2) {
    if ("string" === typeof d2 && "" !== d2 || "number" === typeof d2) return a2 = a2.get(c2) || null, h(b2, a2, "" + d2, e2);
    if ("object" === typeof d2 && null !== d2) {
      switch (d2.$$typeof) {
        case va:
          return a2 = a2.get(null === d2.key ? c2 : d2.key) || null, k2(b2, a2, d2, e2);
        case wa:
          return a2 = a2.get(null === d2.key ? c2 : d2.key) || null, l2(b2, a2, d2, e2);
        case Ha:
          var f3 = d2._init;
          return y2(a2, b2, c2, f3(d2._payload), e2);
      }
      if (eb(d2) || Ka(d2)) return a2 = a2.get(c2) || null, m2(b2, a2, d2, e2, null);
      Mg(b2, d2);
    }
    return null;
  }
  function n2(e2, g2, h2, k3) {
    for (var l3 = null, m3 = null, u2 = g2, w2 = g2 = 0, x2 = null; null !== u2 && w2 < h2.length; w2++) {
      u2.index > w2 ? (x2 = u2, u2 = null) : x2 = u2.sibling;
      var n3 = r2(e2, u2, h2[w2], k3);
      if (null === n3) {
        null === u2 && (u2 = x2);
        break;
      }
      a && u2 && null === n3.alternate && b(e2, u2);
      g2 = f2(n3, g2, w2);
      null === m3 ? l3 = n3 : m3.sibling = n3;
      m3 = n3;
      u2 = x2;
    }
    if (w2 === h2.length) return c(e2, u2), I && tg(e2, w2), l3;
    if (null === u2) {
      for (; w2 < h2.length; w2++) u2 = q2(e2, h2[w2], k3), null !== u2 && (g2 = f2(u2, g2, w2), null === m3 ? l3 = u2 : m3.sibling = u2, m3 = u2);
      I && tg(e2, w2);
      return l3;
    }
    for (u2 = d(e2, u2); w2 < h2.length; w2++) x2 = y2(u2, e2, w2, h2[w2], k3), null !== x2 && (a && null !== x2.alternate && u2.delete(null === x2.key ? w2 : x2.key), g2 = f2(x2, g2, w2), null === m3 ? l3 = x2 : m3.sibling = x2, m3 = x2);
    a && u2.forEach(function(a2) {
      return b(e2, a2);
    });
    I && tg(e2, w2);
    return l3;
  }
  function t2(e2, g2, h2, k3) {
    var l3 = Ka(h2);
    if ("function" !== typeof l3) throw Error(p(150));
    h2 = l3.call(h2);
    if (null == h2) throw Error(p(151));
    for (var u2 = l3 = null, m3 = g2, w2 = g2 = 0, x2 = null, n3 = h2.next(); null !== m3 && !n3.done; w2++, n3 = h2.next()) {
      m3.index > w2 ? (x2 = m3, m3 = null) : x2 = m3.sibling;
      var t3 = r2(e2, m3, n3.value, k3);
      if (null === t3) {
        null === m3 && (m3 = x2);
        break;
      }
      a && m3 && null === t3.alternate && b(e2, m3);
      g2 = f2(t3, g2, w2);
      null === u2 ? l3 = t3 : u2.sibling = t3;
      u2 = t3;
      m3 = x2;
    }
    if (n3.done) return c(
      e2,
      m3
    ), I && tg(e2, w2), l3;
    if (null === m3) {
      for (; !n3.done; w2++, n3 = h2.next()) n3 = q2(e2, n3.value, k3), null !== n3 && (g2 = f2(n3, g2, w2), null === u2 ? l3 = n3 : u2.sibling = n3, u2 = n3);
      I && tg(e2, w2);
      return l3;
    }
    for (m3 = d(e2, m3); !n3.done; w2++, n3 = h2.next()) n3 = y2(m3, e2, w2, n3.value, k3), null !== n3 && (a && null !== n3.alternate && m3.delete(null === n3.key ? w2 : n3.key), g2 = f2(n3, g2, w2), null === u2 ? l3 = n3 : u2.sibling = n3, u2 = n3);
    a && m3.forEach(function(a2) {
      return b(e2, a2);
    });
    I && tg(e2, w2);
    return l3;
  }
  function J2(a2, d2, f3, h2) {
    "object" === typeof f3 && null !== f3 && f3.type === ya && null === f3.key && (f3 = f3.props.children);
    if ("object" === typeof f3 && null !== f3) {
      switch (f3.$$typeof) {
        case va:
          a: {
            for (var k3 = f3.key, l3 = d2; null !== l3; ) {
              if (l3.key === k3) {
                k3 = f3.type;
                if (k3 === ya) {
                  if (7 === l3.tag) {
                    c(a2, l3.sibling);
                    d2 = e(l3, f3.props.children);
                    d2.return = a2;
                    a2 = d2;
                    break a;
                  }
                } else if (l3.elementType === k3 || "object" === typeof k3 && null !== k3 && k3.$$typeof === Ha && Ng(k3) === l3.type) {
                  c(a2, l3.sibling);
                  d2 = e(l3, f3.props);
                  d2.ref = Lg(a2, l3, f3);
                  d2.return = a2;
                  a2 = d2;
                  break a;
                }
                c(a2, l3);
                break;
              } else b(a2, l3);
              l3 = l3.sibling;
            }
            f3.type === ya ? (d2 = Tg(f3.props.children, a2.mode, h2, f3.key), d2.return = a2, a2 = d2) : (h2 = Rg(f3.type, f3.key, f3.props, null, a2.mode, h2), h2.ref = Lg(a2, d2, f3), h2.return = a2, a2 = h2);
          }
          return g(a2);
        case wa:
          a: {
            for (l3 = f3.key; null !== d2; ) {
              if (d2.key === l3) if (4 === d2.tag && d2.stateNode.containerInfo === f3.containerInfo && d2.stateNode.implementation === f3.implementation) {
                c(a2, d2.sibling);
                d2 = e(d2, f3.children || []);
                d2.return = a2;
                a2 = d2;
                break a;
              } else {
                c(a2, d2);
                break;
              }
              else b(a2, d2);
              d2 = d2.sibling;
            }
            d2 = Sg(f3, a2.mode, h2);
            d2.return = a2;
            a2 = d2;
          }
          return g(a2);
        case Ha:
          return l3 = f3._init, J2(a2, d2, l3(f3._payload), h2);
      }
      if (eb(f3)) return n2(a2, d2, f3, h2);
      if (Ka(f3)) return t2(a2, d2, f3, h2);
      Mg(a2, f3);
    }
    return "string" === typeof f3 && "" !== f3 || "number" === typeof f3 ? (f3 = "" + f3, null !== d2 && 6 === d2.tag ? (c(a2, d2.sibling), d2 = e(d2, f3), d2.return = a2, a2 = d2) : (c(a2, d2), d2 = Qg(f3, a2.mode, h2), d2.return = a2, a2 = d2), g(a2)) : c(a2, d2);
  }
  return J2;
}
var Ug = Og(true), Vg = Og(false), Wg = Uf(null), Xg = null, Yg = null, Zg = null;
function $g() {
  Zg = Yg = Xg = null;
}
function ah(a) {
  var b = Wg.current;
  E(Wg);
  a._currentValue = b;
}
function bh(a, b, c) {
  for (; null !== a; ) {
    var d = a.alternate;
    (a.childLanes & b) !== b ? (a.childLanes |= b, null !== d && (d.childLanes |= b)) : null !== d && (d.childLanes & b) !== b && (d.childLanes |= b);
    if (a === c) break;
    a = a.return;
  }
}
function ch(a, b) {
  Xg = a;
  Zg = Yg = null;
  a = a.dependencies;
  null !== a && null !== a.firstContext && (0 !== (a.lanes & b) && (dh = true), a.firstContext = null);
}
function eh(a) {
  var b = a._currentValue;
  if (Zg !== a) if (a = { context: a, memoizedValue: b, next: null }, null === Yg) {
    if (null === Xg) throw Error(p(308));
    Yg = a;
    Xg.dependencies = { lanes: 0, firstContext: a };
  } else Yg = Yg.next = a;
  return b;
}
var fh = null;
function gh(a) {
  null === fh ? fh = [a] : fh.push(a);
}
function hh(a, b, c, d) {
  var e = b.interleaved;
  null === e ? (c.next = c, gh(b)) : (c.next = e.next, e.next = c);
  b.interleaved = c;
  return ih(a, d);
}
function ih(a, b) {
  a.lanes |= b;
  var c = a.alternate;
  null !== c && (c.lanes |= b);
  c = a;
  for (a = a.return; null !== a; ) a.childLanes |= b, c = a.alternate, null !== c && (c.childLanes |= b), c = a, a = a.return;
  return 3 === c.tag ? c.stateNode : null;
}
var jh = false;
function kh(a) {
  a.updateQueue = { baseState: a.memoizedState, firstBaseUpdate: null, lastBaseUpdate: null, shared: { pending: null, interleaved: null, lanes: 0 }, effects: null };
}
function lh(a, b) {
  a = a.updateQueue;
  b.updateQueue === a && (b.updateQueue = { baseState: a.baseState, firstBaseUpdate: a.firstBaseUpdate, lastBaseUpdate: a.lastBaseUpdate, shared: a.shared, effects: a.effects });
}
function mh(a, b) {
  return { eventTime: a, lane: b, tag: 0, payload: null, callback: null, next: null };
}
function nh(a, b, c) {
  var d = a.updateQueue;
  if (null === d) return null;
  d = d.shared;
  if (0 !== (K & 2)) {
    var e = d.pending;
    null === e ? b.next = b : (b.next = e.next, e.next = b);
    d.pending = b;
    return ih(a, c);
  }
  e = d.interleaved;
  null === e ? (b.next = b, gh(d)) : (b.next = e.next, e.next = b);
  d.interleaved = b;
  return ih(a, c);
}
function oh(a, b, c) {
  b = b.updateQueue;
  if (null !== b && (b = b.shared, 0 !== (c & 4194240))) {
    var d = b.lanes;
    d &= a.pendingLanes;
    c |= d;
    b.lanes = c;
    Cc(a, c);
  }
}
function ph(a, b) {
  var c = a.updateQueue, d = a.alternate;
  if (null !== d && (d = d.updateQueue, c === d)) {
    var e = null, f2 = null;
    c = c.firstBaseUpdate;
    if (null !== c) {
      do {
        var g = { eventTime: c.eventTime, lane: c.lane, tag: c.tag, payload: c.payload, callback: c.callback, next: null };
        null === f2 ? e = f2 = g : f2 = f2.next = g;
        c = c.next;
      } while (null !== c);
      null === f2 ? e = f2 = b : f2 = f2.next = b;
    } else e = f2 = b;
    c = { baseState: d.baseState, firstBaseUpdate: e, lastBaseUpdate: f2, shared: d.shared, effects: d.effects };
    a.updateQueue = c;
    return;
  }
  a = c.lastBaseUpdate;
  null === a ? c.firstBaseUpdate = b : a.next = b;
  c.lastBaseUpdate = b;
}
function qh(a, b, c, d) {
  var e = a.updateQueue;
  jh = false;
  var f2 = e.firstBaseUpdate, g = e.lastBaseUpdate, h = e.shared.pending;
  if (null !== h) {
    e.shared.pending = null;
    var k2 = h, l2 = k2.next;
    k2.next = null;
    null === g ? f2 = l2 : g.next = l2;
    g = k2;
    var m2 = a.alternate;
    null !== m2 && (m2 = m2.updateQueue, h = m2.lastBaseUpdate, h !== g && (null === h ? m2.firstBaseUpdate = l2 : h.next = l2, m2.lastBaseUpdate = k2));
  }
  if (null !== f2) {
    var q2 = e.baseState;
    g = 0;
    m2 = l2 = k2 = null;
    h = f2;
    do {
      var r2 = h.lane, y2 = h.eventTime;
      if ((d & r2) === r2) {
        null !== m2 && (m2 = m2.next = {
          eventTime: y2,
          lane: 0,
          tag: h.tag,
          payload: h.payload,
          callback: h.callback,
          next: null
        });
        a: {
          var n2 = a, t2 = h;
          r2 = b;
          y2 = c;
          switch (t2.tag) {
            case 1:
              n2 = t2.payload;
              if ("function" === typeof n2) {
                q2 = n2.call(y2, q2, r2);
                break a;
              }
              q2 = n2;
              break a;
            case 3:
              n2.flags = n2.flags & -65537 | 128;
            case 0:
              n2 = t2.payload;
              r2 = "function" === typeof n2 ? n2.call(y2, q2, r2) : n2;
              if (null === r2 || void 0 === r2) break a;
              q2 = A({}, q2, r2);
              break a;
            case 2:
              jh = true;
          }
        }
        null !== h.callback && 0 !== h.lane && (a.flags |= 64, r2 = e.effects, null === r2 ? e.effects = [h] : r2.push(h));
      } else y2 = { eventTime: y2, lane: r2, tag: h.tag, payload: h.payload, callback: h.callback, next: null }, null === m2 ? (l2 = m2 = y2, k2 = q2) : m2 = m2.next = y2, g |= r2;
      h = h.next;
      if (null === h) if (h = e.shared.pending, null === h) break;
      else r2 = h, h = r2.next, r2.next = null, e.lastBaseUpdate = r2, e.shared.pending = null;
    } while (1);
    null === m2 && (k2 = q2);
    e.baseState = k2;
    e.firstBaseUpdate = l2;
    e.lastBaseUpdate = m2;
    b = e.shared.interleaved;
    if (null !== b) {
      e = b;
      do
        g |= e.lane, e = e.next;
      while (e !== b);
    } else null === f2 && (e.shared.lanes = 0);
    rh |= g;
    a.lanes = g;
    a.memoizedState = q2;
  }
}
function sh(a, b, c) {
  a = b.effects;
  b.effects = null;
  if (null !== a) for (b = 0; b < a.length; b++) {
    var d = a[b], e = d.callback;
    if (null !== e) {
      d.callback = null;
      d = c;
      if ("function" !== typeof e) throw Error(p(191, e));
      e.call(d);
    }
  }
}
var th = {}, uh = Uf(th), vh = Uf(th), wh = Uf(th);
function xh(a) {
  if (a === th) throw Error(p(174));
  return a;
}
function yh(a, b) {
  G(wh, b);
  G(vh, a);
  G(uh, th);
  a = b.nodeType;
  switch (a) {
    case 9:
    case 11:
      b = (b = b.documentElement) ? b.namespaceURI : lb(null, "");
      break;
    default:
      a = 8 === a ? b.parentNode : b, b = a.namespaceURI || null, a = a.tagName, b = lb(b, a);
  }
  E(uh);
  G(uh, b);
}
function zh() {
  E(uh);
  E(vh);
  E(wh);
}
function Ah(a) {
  xh(wh.current);
  var b = xh(uh.current);
  var c = lb(b, a.type);
  b !== c && (G(vh, a), G(uh, c));
}
function Bh(a) {
  vh.current === a && (E(uh), E(vh));
}
var L = Uf(0);
function Ch(a) {
  for (var b = a; null !== b; ) {
    if (13 === b.tag) {
      var c = b.memoizedState;
      if (null !== c && (c = c.dehydrated, null === c || "$?" === c.data || "$!" === c.data)) return b;
    } else if (19 === b.tag && void 0 !== b.memoizedProps.revealOrder) {
      if (0 !== (b.flags & 128)) return b;
    } else if (null !== b.child) {
      b.child.return = b;
      b = b.child;
      continue;
    }
    if (b === a) break;
    for (; null === b.sibling; ) {
      if (null === b.return || b.return === a) return null;
      b = b.return;
    }
    b.sibling.return = b.return;
    b = b.sibling;
  }
  return null;
}
var Dh = [];
function Eh() {
  for (var a = 0; a < Dh.length; a++) Dh[a]._workInProgressVersionPrimary = null;
  Dh.length = 0;
}
var Fh = ua.ReactCurrentDispatcher, Gh = ua.ReactCurrentBatchConfig, Hh = 0, M = null, N = null, O = null, Ih = false, Jh = false, Kh = 0, Lh = 0;
function P() {
  throw Error(p(321));
}
function Mh(a, b) {
  if (null === b) return false;
  for (var c = 0; c < b.length && c < a.length; c++) if (!He(a[c], b[c])) return false;
  return true;
}
function Nh(a, b, c, d, e, f2) {
  Hh = f2;
  M = b;
  b.memoizedState = null;
  b.updateQueue = null;
  b.lanes = 0;
  Fh.current = null === a || null === a.memoizedState ? Oh : Ph;
  a = c(d, e);
  if (Jh) {
    f2 = 0;
    do {
      Jh = false;
      Kh = 0;
      if (25 <= f2) throw Error(p(301));
      f2 += 1;
      O = N = null;
      b.updateQueue = null;
      Fh.current = Qh;
      a = c(d, e);
    } while (Jh);
  }
  Fh.current = Rh;
  b = null !== N && null !== N.next;
  Hh = 0;
  O = N = M = null;
  Ih = false;
  if (b) throw Error(p(300));
  return a;
}
function Sh() {
  var a = 0 !== Kh;
  Kh = 0;
  return a;
}
function Th() {
  var a = { memoizedState: null, baseState: null, baseQueue: null, queue: null, next: null };
  null === O ? M.memoizedState = O = a : O = O.next = a;
  return O;
}
function Uh() {
  if (null === N) {
    var a = M.alternate;
    a = null !== a ? a.memoizedState : null;
  } else a = N.next;
  var b = null === O ? M.memoizedState : O.next;
  if (null !== b) O = b, N = a;
  else {
    if (null === a) throw Error(p(310));
    N = a;
    a = { memoizedState: N.memoizedState, baseState: N.baseState, baseQueue: N.baseQueue, queue: N.queue, next: null };
    null === O ? M.memoizedState = O = a : O = O.next = a;
  }
  return O;
}
function Vh(a, b) {
  return "function" === typeof b ? b(a) : b;
}
function Wh(a) {
  var b = Uh(), c = b.queue;
  if (null === c) throw Error(p(311));
  c.lastRenderedReducer = a;
  var d = N, e = d.baseQueue, f2 = c.pending;
  if (null !== f2) {
    if (null !== e) {
      var g = e.next;
      e.next = f2.next;
      f2.next = g;
    }
    d.baseQueue = e = f2;
    c.pending = null;
  }
  if (null !== e) {
    f2 = e.next;
    d = d.baseState;
    var h = g = null, k2 = null, l2 = f2;
    do {
      var m2 = l2.lane;
      if ((Hh & m2) === m2) null !== k2 && (k2 = k2.next = { lane: 0, action: l2.action, hasEagerState: l2.hasEagerState, eagerState: l2.eagerState, next: null }), d = l2.hasEagerState ? l2.eagerState : a(d, l2.action);
      else {
        var q2 = {
          lane: m2,
          action: l2.action,
          hasEagerState: l2.hasEagerState,
          eagerState: l2.eagerState,
          next: null
        };
        null === k2 ? (h = k2 = q2, g = d) : k2 = k2.next = q2;
        M.lanes |= m2;
        rh |= m2;
      }
      l2 = l2.next;
    } while (null !== l2 && l2 !== f2);
    null === k2 ? g = d : k2.next = h;
    He(d, b.memoizedState) || (dh = true);
    b.memoizedState = d;
    b.baseState = g;
    b.baseQueue = k2;
    c.lastRenderedState = d;
  }
  a = c.interleaved;
  if (null !== a) {
    e = a;
    do
      f2 = e.lane, M.lanes |= f2, rh |= f2, e = e.next;
    while (e !== a);
  } else null === e && (c.lanes = 0);
  return [b.memoizedState, c.dispatch];
}
function Xh(a) {
  var b = Uh(), c = b.queue;
  if (null === c) throw Error(p(311));
  c.lastRenderedReducer = a;
  var d = c.dispatch, e = c.pending, f2 = b.memoizedState;
  if (null !== e) {
    c.pending = null;
    var g = e = e.next;
    do
      f2 = a(f2, g.action), g = g.next;
    while (g !== e);
    He(f2, b.memoizedState) || (dh = true);
    b.memoizedState = f2;
    null === b.baseQueue && (b.baseState = f2);
    c.lastRenderedState = f2;
  }
  return [f2, d];
}
function Yh() {
}
function Zh(a, b) {
  var c = M, d = Uh(), e = b(), f2 = !He(d.memoizedState, e);
  f2 && (d.memoizedState = e, dh = true);
  d = d.queue;
  $h(ai.bind(null, c, d, a), [a]);
  if (d.getSnapshot !== b || f2 || null !== O && O.memoizedState.tag & 1) {
    c.flags |= 2048;
    bi(9, ci.bind(null, c, d, e, b), void 0, null);
    if (null === Q) throw Error(p(349));
    0 !== (Hh & 30) || di(c, b, e);
  }
  return e;
}
function di(a, b, c) {
  a.flags |= 16384;
  a = { getSnapshot: b, value: c };
  b = M.updateQueue;
  null === b ? (b = { lastEffect: null, stores: null }, M.updateQueue = b, b.stores = [a]) : (c = b.stores, null === c ? b.stores = [a] : c.push(a));
}
function ci(a, b, c, d) {
  b.value = c;
  b.getSnapshot = d;
  ei(b) && fi(a);
}
function ai(a, b, c) {
  return c(function() {
    ei(b) && fi(a);
  });
}
function ei(a) {
  var b = a.getSnapshot;
  a = a.value;
  try {
    var c = b();
    return !He(a, c);
  } catch (d) {
    return true;
  }
}
function fi(a) {
  var b = ih(a, 1);
  null !== b && gi(b, a, 1, -1);
}
function hi(a) {
  var b = Th();
  "function" === typeof a && (a = a());
  b.memoizedState = b.baseState = a;
  a = { pending: null, interleaved: null, lanes: 0, dispatch: null, lastRenderedReducer: Vh, lastRenderedState: a };
  b.queue = a;
  a = a.dispatch = ii.bind(null, M, a);
  return [b.memoizedState, a];
}
function bi(a, b, c, d) {
  a = { tag: a, create: b, destroy: c, deps: d, next: null };
  b = M.updateQueue;
  null === b ? (b = { lastEffect: null, stores: null }, M.updateQueue = b, b.lastEffect = a.next = a) : (c = b.lastEffect, null === c ? b.lastEffect = a.next = a : (d = c.next, c.next = a, a.next = d, b.lastEffect = a));
  return a;
}
function ji() {
  return Uh().memoizedState;
}
function ki(a, b, c, d) {
  var e = Th();
  M.flags |= a;
  e.memoizedState = bi(1 | b, c, void 0, void 0 === d ? null : d);
}
function li(a, b, c, d) {
  var e = Uh();
  d = void 0 === d ? null : d;
  var f2 = void 0;
  if (null !== N) {
    var g = N.memoizedState;
    f2 = g.destroy;
    if (null !== d && Mh(d, g.deps)) {
      e.memoizedState = bi(b, c, f2, d);
      return;
    }
  }
  M.flags |= a;
  e.memoizedState = bi(1 | b, c, f2, d);
}
function mi(a, b) {
  return ki(8390656, 8, a, b);
}
function $h(a, b) {
  return li(2048, 8, a, b);
}
function ni(a, b) {
  return li(4, 2, a, b);
}
function oi(a, b) {
  return li(4, 4, a, b);
}
function pi(a, b) {
  if ("function" === typeof b) return a = a(), b(a), function() {
    b(null);
  };
  if (null !== b && void 0 !== b) return a = a(), b.current = a, function() {
    b.current = null;
  };
}
function qi(a, b, c) {
  c = null !== c && void 0 !== c ? c.concat([a]) : null;
  return li(4, 4, pi.bind(null, b, a), c);
}
function ri() {
}
function si(a, b) {
  var c = Uh();
  b = void 0 === b ? null : b;
  var d = c.memoizedState;
  if (null !== d && null !== b && Mh(b, d[1])) return d[0];
  c.memoizedState = [a, b];
  return a;
}
function ti(a, b) {
  var c = Uh();
  b = void 0 === b ? null : b;
  var d = c.memoizedState;
  if (null !== d && null !== b && Mh(b, d[1])) return d[0];
  a = a();
  c.memoizedState = [a, b];
  return a;
}
function ui(a, b, c) {
  if (0 === (Hh & 21)) return a.baseState && (a.baseState = false, dh = true), a.memoizedState = c;
  He(c, b) || (c = yc(), M.lanes |= c, rh |= c, a.baseState = true);
  return b;
}
function vi(a, b) {
  var c = C;
  C = 0 !== c && 4 > c ? c : 4;
  a(true);
  var d = Gh.transition;
  Gh.transition = {};
  try {
    a(false), b();
  } finally {
    C = c, Gh.transition = d;
  }
}
function wi() {
  return Uh().memoizedState;
}
function xi(a, b, c) {
  var d = yi(a);
  c = { lane: d, action: c, hasEagerState: false, eagerState: null, next: null };
  if (zi(a)) Ai(b, c);
  else if (c = hh(a, b, c, d), null !== c) {
    var e = R();
    gi(c, a, d, e);
    Bi(c, b, d);
  }
}
function ii(a, b, c) {
  var d = yi(a), e = { lane: d, action: c, hasEagerState: false, eagerState: null, next: null };
  if (zi(a)) Ai(b, e);
  else {
    var f2 = a.alternate;
    if (0 === a.lanes && (null === f2 || 0 === f2.lanes) && (f2 = b.lastRenderedReducer, null !== f2)) try {
      var g = b.lastRenderedState, h = f2(g, c);
      e.hasEagerState = true;
      e.eagerState = h;
      if (He(h, g)) {
        var k2 = b.interleaved;
        null === k2 ? (e.next = e, gh(b)) : (e.next = k2.next, k2.next = e);
        b.interleaved = e;
        return;
      }
    } catch (l2) {
    } finally {
    }
    c = hh(a, b, e, d);
    null !== c && (e = R(), gi(c, a, d, e), Bi(c, b, d));
  }
}
function zi(a) {
  var b = a.alternate;
  return a === M || null !== b && b === M;
}
function Ai(a, b) {
  Jh = Ih = true;
  var c = a.pending;
  null === c ? b.next = b : (b.next = c.next, c.next = b);
  a.pending = b;
}
function Bi(a, b, c) {
  if (0 !== (c & 4194240)) {
    var d = b.lanes;
    d &= a.pendingLanes;
    c |= d;
    b.lanes = c;
    Cc(a, c);
  }
}
var Rh = { readContext: eh, useCallback: P, useContext: P, useEffect: P, useImperativeHandle: P, useInsertionEffect: P, useLayoutEffect: P, useMemo: P, useReducer: P, useRef: P, useState: P, useDebugValue: P, useDeferredValue: P, useTransition: P, useMutableSource: P, useSyncExternalStore: P, useId: P, unstable_isNewReconciler: false }, Oh = { readContext: eh, useCallback: function(a, b) {
  Th().memoizedState = [a, void 0 === b ? null : b];
  return a;
}, useContext: eh, useEffect: mi, useImperativeHandle: function(a, b, c) {
  c = null !== c && void 0 !== c ? c.concat([a]) : null;
  return ki(
    4194308,
    4,
    pi.bind(null, b, a),
    c
  );
}, useLayoutEffect: function(a, b) {
  return ki(4194308, 4, a, b);
}, useInsertionEffect: function(a, b) {
  return ki(4, 2, a, b);
}, useMemo: function(a, b) {
  var c = Th();
  b = void 0 === b ? null : b;
  a = a();
  c.memoizedState = [a, b];
  return a;
}, useReducer: function(a, b, c) {
  var d = Th();
  b = void 0 !== c ? c(b) : b;
  d.memoizedState = d.baseState = b;
  a = { pending: null, interleaved: null, lanes: 0, dispatch: null, lastRenderedReducer: a, lastRenderedState: b };
  d.queue = a;
  a = a.dispatch = xi.bind(null, M, a);
  return [d.memoizedState, a];
}, useRef: function(a) {
  var b = Th();
  a = { current: a };
  return b.memoizedState = a;
}, useState: hi, useDebugValue: ri, useDeferredValue: function(a) {
  return Th().memoizedState = a;
}, useTransition: function() {
  var a = hi(false), b = a[0];
  a = vi.bind(null, a[1]);
  Th().memoizedState = a;
  return [b, a];
}, useMutableSource: function() {
}, useSyncExternalStore: function(a, b, c) {
  var d = M, e = Th();
  if (I) {
    if (void 0 === c) throw Error(p(407));
    c = c();
  } else {
    c = b();
    if (null === Q) throw Error(p(349));
    0 !== (Hh & 30) || di(d, b, c);
  }
  e.memoizedState = c;
  var f2 = { value: c, getSnapshot: b };
  e.queue = f2;
  mi(ai.bind(
    null,
    d,
    f2,
    a
  ), [a]);
  d.flags |= 2048;
  bi(9, ci.bind(null, d, f2, c, b), void 0, null);
  return c;
}, useId: function() {
  var a = Th(), b = Q.identifierPrefix;
  if (I) {
    var c = sg;
    var d = rg;
    c = (d & ~(1 << 32 - oc(d) - 1)).toString(32) + c;
    b = ":" + b + "R" + c;
    c = Kh++;
    0 < c && (b += "H" + c.toString(32));
    b += ":";
  } else c = Lh++, b = ":" + b + "r" + c.toString(32) + ":";
  return a.memoizedState = b;
}, unstable_isNewReconciler: false }, Ph = {
  readContext: eh,
  useCallback: si,
  useContext: eh,
  useEffect: $h,
  useImperativeHandle: qi,
  useInsertionEffect: ni,
  useLayoutEffect: oi,
  useMemo: ti,
  useReducer: Wh,
  useRef: ji,
  useState: function() {
    return Wh(Vh);
  },
  useDebugValue: ri,
  useDeferredValue: function(a) {
    var b = Uh();
    return ui(b, N.memoizedState, a);
  },
  useTransition: function() {
    var a = Wh(Vh)[0], b = Uh().memoizedState;
    return [a, b];
  },
  useMutableSource: Yh,
  useSyncExternalStore: Zh,
  useId: wi,
  unstable_isNewReconciler: false
}, Qh = { readContext: eh, useCallback: si, useContext: eh, useEffect: $h, useImperativeHandle: qi, useInsertionEffect: ni, useLayoutEffect: oi, useMemo: ti, useReducer: Xh, useRef: ji, useState: function() {
  return Xh(Vh);
}, useDebugValue: ri, useDeferredValue: function(a) {
  var b = Uh();
  return null === N ? b.memoizedState = a : ui(b, N.memoizedState, a);
}, useTransition: function() {
  var a = Xh(Vh)[0], b = Uh().memoizedState;
  return [a, b];
}, useMutableSource: Yh, useSyncExternalStore: Zh, useId: wi, unstable_isNewReconciler: false };
function Ci(a, b) {
  if (a && a.defaultProps) {
    b = A({}, b);
    a = a.defaultProps;
    for (var c in a) void 0 === b[c] && (b[c] = a[c]);
    return b;
  }
  return b;
}
function Di(a, b, c, d) {
  b = a.memoizedState;
  c = c(d, b);
  c = null === c || void 0 === c ? b : A({}, b, c);
  a.memoizedState = c;
  0 === a.lanes && (a.updateQueue.baseState = c);
}
var Ei = { isMounted: function(a) {
  return (a = a._reactInternals) ? Vb(a) === a : false;
}, enqueueSetState: function(a, b, c) {
  a = a._reactInternals;
  var d = R(), e = yi(a), f2 = mh(d, e);
  f2.payload = b;
  void 0 !== c && null !== c && (f2.callback = c);
  b = nh(a, f2, e);
  null !== b && (gi(b, a, e, d), oh(b, a, e));
}, enqueueReplaceState: function(a, b, c) {
  a = a._reactInternals;
  var d = R(), e = yi(a), f2 = mh(d, e);
  f2.tag = 1;
  f2.payload = b;
  void 0 !== c && null !== c && (f2.callback = c);
  b = nh(a, f2, e);
  null !== b && (gi(b, a, e, d), oh(b, a, e));
}, enqueueForceUpdate: function(a, b) {
  a = a._reactInternals;
  var c = R(), d = yi(a), e = mh(c, d);
  e.tag = 2;
  void 0 !== b && null !== b && (e.callback = b);
  b = nh(a, e, d);
  null !== b && (gi(b, a, d, c), oh(b, a, d));
} };
function Fi(a, b, c, d, e, f2, g) {
  a = a.stateNode;
  return "function" === typeof a.shouldComponentUpdate ? a.shouldComponentUpdate(d, f2, g) : b.prototype && b.prototype.isPureReactComponent ? !Ie(c, d) || !Ie(e, f2) : true;
}
function Gi(a, b, c) {
  var d = false, e = Vf;
  var f2 = b.contextType;
  "object" === typeof f2 && null !== f2 ? f2 = eh(f2) : (e = Zf(b) ? Xf : H.current, d = b.contextTypes, f2 = (d = null !== d && void 0 !== d) ? Yf(a, e) : Vf);
  b = new b(c, f2);
  a.memoizedState = null !== b.state && void 0 !== b.state ? b.state : null;
  b.updater = Ei;
  a.stateNode = b;
  b._reactInternals = a;
  d && (a = a.stateNode, a.__reactInternalMemoizedUnmaskedChildContext = e, a.__reactInternalMemoizedMaskedChildContext = f2);
  return b;
}
function Hi(a, b, c, d) {
  a = b.state;
  "function" === typeof b.componentWillReceiveProps && b.componentWillReceiveProps(c, d);
  "function" === typeof b.UNSAFE_componentWillReceiveProps && b.UNSAFE_componentWillReceiveProps(c, d);
  b.state !== a && Ei.enqueueReplaceState(b, b.state, null);
}
function Ii(a, b, c, d) {
  var e = a.stateNode;
  e.props = c;
  e.state = a.memoizedState;
  e.refs = {};
  kh(a);
  var f2 = b.contextType;
  "object" === typeof f2 && null !== f2 ? e.context = eh(f2) : (f2 = Zf(b) ? Xf : H.current, e.context = Yf(a, f2));
  e.state = a.memoizedState;
  f2 = b.getDerivedStateFromProps;
  "function" === typeof f2 && (Di(a, b, f2, c), e.state = a.memoizedState);
  "function" === typeof b.getDerivedStateFromProps || "function" === typeof e.getSnapshotBeforeUpdate || "function" !== typeof e.UNSAFE_componentWillMount && "function" !== typeof e.componentWillMount || (b = e.state, "function" === typeof e.componentWillMount && e.componentWillMount(), "function" === typeof e.UNSAFE_componentWillMount && e.UNSAFE_componentWillMount(), b !== e.state && Ei.enqueueReplaceState(e, e.state, null), qh(a, c, e, d), e.state = a.memoizedState);
  "function" === typeof e.componentDidMount && (a.flags |= 4194308);
}
function Ji(a, b) {
  try {
    var c = "", d = b;
    do
      c += Pa(d), d = d.return;
    while (d);
    var e = c;
  } catch (f2) {
    e = "\nError generating stack: " + f2.message + "\n" + f2.stack;
  }
  return { value: a, source: b, stack: e, digest: null };
}
function Ki(a, b, c) {
  return { value: a, source: null, stack: null != c ? c : null, digest: null != b ? b : null };
}
function Li(a, b) {
  try {
    console.error(b.value);
  } catch (c) {
    setTimeout(function() {
      throw c;
    });
  }
}
var Mi = "function" === typeof WeakMap ? WeakMap : Map;
function Ni(a, b, c) {
  c = mh(-1, c);
  c.tag = 3;
  c.payload = { element: null };
  var d = b.value;
  c.callback = function() {
    Oi || (Oi = true, Pi = d);
    Li(a, b);
  };
  return c;
}
function Qi(a, b, c) {
  c = mh(-1, c);
  c.tag = 3;
  var d = a.type.getDerivedStateFromError;
  if ("function" === typeof d) {
    var e = b.value;
    c.payload = function() {
      return d(e);
    };
    c.callback = function() {
      Li(a, b);
    };
  }
  var f2 = a.stateNode;
  null !== f2 && "function" === typeof f2.componentDidCatch && (c.callback = function() {
    Li(a, b);
    "function" !== typeof d && (null === Ri ? Ri = /* @__PURE__ */ new Set([this]) : Ri.add(this));
    var c2 = b.stack;
    this.componentDidCatch(b.value, { componentStack: null !== c2 ? c2 : "" });
  });
  return c;
}
function Si(a, b, c) {
  var d = a.pingCache;
  if (null === d) {
    d = a.pingCache = new Mi();
    var e = /* @__PURE__ */ new Set();
    d.set(b, e);
  } else e = d.get(b), void 0 === e && (e = /* @__PURE__ */ new Set(), d.set(b, e));
  e.has(c) || (e.add(c), a = Ti.bind(null, a, b, c), b.then(a, a));
}
function Ui(a) {
  do {
    var b;
    if (b = 13 === a.tag) b = a.memoizedState, b = null !== b ? null !== b.dehydrated ? true : false : true;
    if (b) return a;
    a = a.return;
  } while (null !== a);
  return null;
}
function Vi(a, b, c, d, e) {
  if (0 === (a.mode & 1)) return a === b ? a.flags |= 65536 : (a.flags |= 128, c.flags |= 131072, c.flags &= -52805, 1 === c.tag && (null === c.alternate ? c.tag = 17 : (b = mh(-1, 1), b.tag = 2, nh(c, b, 1))), c.lanes |= 1), a;
  a.flags |= 65536;
  a.lanes = e;
  return a;
}
var Wi = ua.ReactCurrentOwner, dh = false;
function Xi(a, b, c, d) {
  b.child = null === a ? Vg(b, null, c, d) : Ug(b, a.child, c, d);
}
function Yi(a, b, c, d, e) {
  c = c.render;
  var f2 = b.ref;
  ch(b, e);
  d = Nh(a, b, c, d, f2, e);
  c = Sh();
  if (null !== a && !dh) return b.updateQueue = a.updateQueue, b.flags &= -2053, a.lanes &= ~e, Zi(a, b, e);
  I && c && vg(b);
  b.flags |= 1;
  Xi(a, b, d, e);
  return b.child;
}
function $i(a, b, c, d, e) {
  if (null === a) {
    var f2 = c.type;
    if ("function" === typeof f2 && !aj(f2) && void 0 === f2.defaultProps && null === c.compare && void 0 === c.defaultProps) return b.tag = 15, b.type = f2, bj(a, b, f2, d, e);
    a = Rg(c.type, null, d, b, b.mode, e);
    a.ref = b.ref;
    a.return = b;
    return b.child = a;
  }
  f2 = a.child;
  if (0 === (a.lanes & e)) {
    var g = f2.memoizedProps;
    c = c.compare;
    c = null !== c ? c : Ie;
    if (c(g, d) && a.ref === b.ref) return Zi(a, b, e);
  }
  b.flags |= 1;
  a = Pg(f2, d);
  a.ref = b.ref;
  a.return = b;
  return b.child = a;
}
function bj(a, b, c, d, e) {
  if (null !== a) {
    var f2 = a.memoizedProps;
    if (Ie(f2, d) && a.ref === b.ref) if (dh = false, b.pendingProps = d = f2, 0 !== (a.lanes & e)) 0 !== (a.flags & 131072) && (dh = true);
    else return b.lanes = a.lanes, Zi(a, b, e);
  }
  return cj(a, b, c, d, e);
}
function dj(a, b, c) {
  var d = b.pendingProps, e = d.children, f2 = null !== a ? a.memoizedState : null;
  if ("hidden" === d.mode) if (0 === (b.mode & 1)) b.memoizedState = { baseLanes: 0, cachePool: null, transitions: null }, G(ej, fj), fj |= c;
  else {
    if (0 === (c & 1073741824)) return a = null !== f2 ? f2.baseLanes | c : c, b.lanes = b.childLanes = 1073741824, b.memoizedState = { baseLanes: a, cachePool: null, transitions: null }, b.updateQueue = null, G(ej, fj), fj |= a, null;
    b.memoizedState = { baseLanes: 0, cachePool: null, transitions: null };
    d = null !== f2 ? f2.baseLanes : c;
    G(ej, fj);
    fj |= d;
  }
  else null !== f2 ? (d = f2.baseLanes | c, b.memoizedState = null) : d = c, G(ej, fj), fj |= d;
  Xi(a, b, e, c);
  return b.child;
}
function gj(a, b) {
  var c = b.ref;
  if (null === a && null !== c || null !== a && a.ref !== c) b.flags |= 512, b.flags |= 2097152;
}
function cj(a, b, c, d, e) {
  var f2 = Zf(c) ? Xf : H.current;
  f2 = Yf(b, f2);
  ch(b, e);
  c = Nh(a, b, c, d, f2, e);
  d = Sh();
  if (null !== a && !dh) return b.updateQueue = a.updateQueue, b.flags &= -2053, a.lanes &= ~e, Zi(a, b, e);
  I && d && vg(b);
  b.flags |= 1;
  Xi(a, b, c, e);
  return b.child;
}
function hj(a, b, c, d, e) {
  if (Zf(c)) {
    var f2 = true;
    cg(b);
  } else f2 = false;
  ch(b, e);
  if (null === b.stateNode) ij(a, b), Gi(b, c, d), Ii(b, c, d, e), d = true;
  else if (null === a) {
    var g = b.stateNode, h = b.memoizedProps;
    g.props = h;
    var k2 = g.context, l2 = c.contextType;
    "object" === typeof l2 && null !== l2 ? l2 = eh(l2) : (l2 = Zf(c) ? Xf : H.current, l2 = Yf(b, l2));
    var m2 = c.getDerivedStateFromProps, q2 = "function" === typeof m2 || "function" === typeof g.getSnapshotBeforeUpdate;
    q2 || "function" !== typeof g.UNSAFE_componentWillReceiveProps && "function" !== typeof g.componentWillReceiveProps || (h !== d || k2 !== l2) && Hi(b, g, d, l2);
    jh = false;
    var r2 = b.memoizedState;
    g.state = r2;
    qh(b, d, g, e);
    k2 = b.memoizedState;
    h !== d || r2 !== k2 || Wf.current || jh ? ("function" === typeof m2 && (Di(b, c, m2, d), k2 = b.memoizedState), (h = jh || Fi(b, c, h, d, r2, k2, l2)) ? (q2 || "function" !== typeof g.UNSAFE_componentWillMount && "function" !== typeof g.componentWillMount || ("function" === typeof g.componentWillMount && g.componentWillMount(), "function" === typeof g.UNSAFE_componentWillMount && g.UNSAFE_componentWillMount()), "function" === typeof g.componentDidMount && (b.flags |= 4194308)) : ("function" === typeof g.componentDidMount && (b.flags |= 4194308), b.memoizedProps = d, b.memoizedState = k2), g.props = d, g.state = k2, g.context = l2, d = h) : ("function" === typeof g.componentDidMount && (b.flags |= 4194308), d = false);
  } else {
    g = b.stateNode;
    lh(a, b);
    h = b.memoizedProps;
    l2 = b.type === b.elementType ? h : Ci(b.type, h);
    g.props = l2;
    q2 = b.pendingProps;
    r2 = g.context;
    k2 = c.contextType;
    "object" === typeof k2 && null !== k2 ? k2 = eh(k2) : (k2 = Zf(c) ? Xf : H.current, k2 = Yf(b, k2));
    var y2 = c.getDerivedStateFromProps;
    (m2 = "function" === typeof y2 || "function" === typeof g.getSnapshotBeforeUpdate) || "function" !== typeof g.UNSAFE_componentWillReceiveProps && "function" !== typeof g.componentWillReceiveProps || (h !== q2 || r2 !== k2) && Hi(b, g, d, k2);
    jh = false;
    r2 = b.memoizedState;
    g.state = r2;
    qh(b, d, g, e);
    var n2 = b.memoizedState;
    h !== q2 || r2 !== n2 || Wf.current || jh ? ("function" === typeof y2 && (Di(b, c, y2, d), n2 = b.memoizedState), (l2 = jh || Fi(b, c, l2, d, r2, n2, k2) || false) ? (m2 || "function" !== typeof g.UNSAFE_componentWillUpdate && "function" !== typeof g.componentWillUpdate || ("function" === typeof g.componentWillUpdate && g.componentWillUpdate(d, n2, k2), "function" === typeof g.UNSAFE_componentWillUpdate && g.UNSAFE_componentWillUpdate(d, n2, k2)), "function" === typeof g.componentDidUpdate && (b.flags |= 4), "function" === typeof g.getSnapshotBeforeUpdate && (b.flags |= 1024)) : ("function" !== typeof g.componentDidUpdate || h === a.memoizedProps && r2 === a.memoizedState || (b.flags |= 4), "function" !== typeof g.getSnapshotBeforeUpdate || h === a.memoizedProps && r2 === a.memoizedState || (b.flags |= 1024), b.memoizedProps = d, b.memoizedState = n2), g.props = d, g.state = n2, g.context = k2, d = l2) : ("function" !== typeof g.componentDidUpdate || h === a.memoizedProps && r2 === a.memoizedState || (b.flags |= 4), "function" !== typeof g.getSnapshotBeforeUpdate || h === a.memoizedProps && r2 === a.memoizedState || (b.flags |= 1024), d = false);
  }
  return jj(a, b, c, d, f2, e);
}
function jj(a, b, c, d, e, f2) {
  gj(a, b);
  var g = 0 !== (b.flags & 128);
  if (!d && !g) return e && dg(b, c, false), Zi(a, b, f2);
  d = b.stateNode;
  Wi.current = b;
  var h = g && "function" !== typeof c.getDerivedStateFromError ? null : d.render();
  b.flags |= 1;
  null !== a && g ? (b.child = Ug(b, a.child, null, f2), b.child = Ug(b, null, h, f2)) : Xi(a, b, h, f2);
  b.memoizedState = d.state;
  e && dg(b, c, true);
  return b.child;
}
function kj(a) {
  var b = a.stateNode;
  b.pendingContext ? ag(a, b.pendingContext, b.pendingContext !== b.context) : b.context && ag(a, b.context, false);
  yh(a, b.containerInfo);
}
function lj(a, b, c, d, e) {
  Ig();
  Jg(e);
  b.flags |= 256;
  Xi(a, b, c, d);
  return b.child;
}
var mj = { dehydrated: null, treeContext: null, retryLane: 0 };
function nj(a) {
  return { baseLanes: a, cachePool: null, transitions: null };
}
function oj(a, b, c) {
  var d = b.pendingProps, e = L.current, f2 = false, g = 0 !== (b.flags & 128), h;
  (h = g) || (h = null !== a && null === a.memoizedState ? false : 0 !== (e & 2));
  if (h) f2 = true, b.flags &= -129;
  else if (null === a || null !== a.memoizedState) e |= 1;
  G(L, e & 1);
  if (null === a) {
    Eg(b);
    a = b.memoizedState;
    if (null !== a && (a = a.dehydrated, null !== a)) return 0 === (b.mode & 1) ? b.lanes = 1 : "$!" === a.data ? b.lanes = 8 : b.lanes = 1073741824, null;
    g = d.children;
    a = d.fallback;
    return f2 ? (d = b.mode, f2 = b.child, g = { mode: "hidden", children: g }, 0 === (d & 1) && null !== f2 ? (f2.childLanes = 0, f2.pendingProps = g) : f2 = pj(g, d, 0, null), a = Tg(a, d, c, null), f2.return = b, a.return = b, f2.sibling = a, b.child = f2, b.child.memoizedState = nj(c), b.memoizedState = mj, a) : qj(b, g);
  }
  e = a.memoizedState;
  if (null !== e && (h = e.dehydrated, null !== h)) return rj(a, b, g, d, h, e, c);
  if (f2) {
    f2 = d.fallback;
    g = b.mode;
    e = a.child;
    h = e.sibling;
    var k2 = { mode: "hidden", children: d.children };
    0 === (g & 1) && b.child !== e ? (d = b.child, d.childLanes = 0, d.pendingProps = k2, b.deletions = null) : (d = Pg(e, k2), d.subtreeFlags = e.subtreeFlags & 14680064);
    null !== h ? f2 = Pg(h, f2) : (f2 = Tg(f2, g, c, null), f2.flags |= 2);
    f2.return = b;
    d.return = b;
    d.sibling = f2;
    b.child = d;
    d = f2;
    f2 = b.child;
    g = a.child.memoizedState;
    g = null === g ? nj(c) : { baseLanes: g.baseLanes | c, cachePool: null, transitions: g.transitions };
    f2.memoizedState = g;
    f2.childLanes = a.childLanes & ~c;
    b.memoizedState = mj;
    return d;
  }
  f2 = a.child;
  a = f2.sibling;
  d = Pg(f2, { mode: "visible", children: d.children });
  0 === (b.mode & 1) && (d.lanes = c);
  d.return = b;
  d.sibling = null;
  null !== a && (c = b.deletions, null === c ? (b.deletions = [a], b.flags |= 16) : c.push(a));
  b.child = d;
  b.memoizedState = null;
  return d;
}
function qj(a, b) {
  b = pj({ mode: "visible", children: b }, a.mode, 0, null);
  b.return = a;
  return a.child = b;
}
function sj(a, b, c, d) {
  null !== d && Jg(d);
  Ug(b, a.child, null, c);
  a = qj(b, b.pendingProps.children);
  a.flags |= 2;
  b.memoizedState = null;
  return a;
}
function rj(a, b, c, d, e, f2, g) {
  if (c) {
    if (b.flags & 256) return b.flags &= -257, d = Ki(Error(p(422))), sj(a, b, g, d);
    if (null !== b.memoizedState) return b.child = a.child, b.flags |= 128, null;
    f2 = d.fallback;
    e = b.mode;
    d = pj({ mode: "visible", children: d.children }, e, 0, null);
    f2 = Tg(f2, e, g, null);
    f2.flags |= 2;
    d.return = b;
    f2.return = b;
    d.sibling = f2;
    b.child = d;
    0 !== (b.mode & 1) && Ug(b, a.child, null, g);
    b.child.memoizedState = nj(g);
    b.memoizedState = mj;
    return f2;
  }
  if (0 === (b.mode & 1)) return sj(a, b, g, null);
  if ("$!" === e.data) {
    d = e.nextSibling && e.nextSibling.dataset;
    if (d) var h = d.dgst;
    d = h;
    f2 = Error(p(419));
    d = Ki(f2, d, void 0);
    return sj(a, b, g, d);
  }
  h = 0 !== (g & a.childLanes);
  if (dh || h) {
    d = Q;
    if (null !== d) {
      switch (g & -g) {
        case 4:
          e = 2;
          break;
        case 16:
          e = 8;
          break;
        case 64:
        case 128:
        case 256:
        case 512:
        case 1024:
        case 2048:
        case 4096:
        case 8192:
        case 16384:
        case 32768:
        case 65536:
        case 131072:
        case 262144:
        case 524288:
        case 1048576:
        case 2097152:
        case 4194304:
        case 8388608:
        case 16777216:
        case 33554432:
        case 67108864:
          e = 32;
          break;
        case 536870912:
          e = 268435456;
          break;
        default:
          e = 0;
      }
      e = 0 !== (e & (d.suspendedLanes | g)) ? 0 : e;
      0 !== e && e !== f2.retryLane && (f2.retryLane = e, ih(a, e), gi(d, a, e, -1));
    }
    tj();
    d = Ki(Error(p(421)));
    return sj(a, b, g, d);
  }
  if ("$?" === e.data) return b.flags |= 128, b.child = a.child, b = uj.bind(null, a), e._reactRetry = b, null;
  a = f2.treeContext;
  yg = Lf(e.nextSibling);
  xg = b;
  I = true;
  zg = null;
  null !== a && (og[pg++] = rg, og[pg++] = sg, og[pg++] = qg, rg = a.id, sg = a.overflow, qg = b);
  b = qj(b, d.children);
  b.flags |= 4096;
  return b;
}
function vj(a, b, c) {
  a.lanes |= b;
  var d = a.alternate;
  null !== d && (d.lanes |= b);
  bh(a.return, b, c);
}
function wj(a, b, c, d, e) {
  var f2 = a.memoizedState;
  null === f2 ? a.memoizedState = { isBackwards: b, rendering: null, renderingStartTime: 0, last: d, tail: c, tailMode: e } : (f2.isBackwards = b, f2.rendering = null, f2.renderingStartTime = 0, f2.last = d, f2.tail = c, f2.tailMode = e);
}
function xj(a, b, c) {
  var d = b.pendingProps, e = d.revealOrder, f2 = d.tail;
  Xi(a, b, d.children, c);
  d = L.current;
  if (0 !== (d & 2)) d = d & 1 | 2, b.flags |= 128;
  else {
    if (null !== a && 0 !== (a.flags & 128)) a: for (a = b.child; null !== a; ) {
      if (13 === a.tag) null !== a.memoizedState && vj(a, c, b);
      else if (19 === a.tag) vj(a, c, b);
      else if (null !== a.child) {
        a.child.return = a;
        a = a.child;
        continue;
      }
      if (a === b) break a;
      for (; null === a.sibling; ) {
        if (null === a.return || a.return === b) break a;
        a = a.return;
      }
      a.sibling.return = a.return;
      a = a.sibling;
    }
    d &= 1;
  }
  G(L, d);
  if (0 === (b.mode & 1)) b.memoizedState = null;
  else switch (e) {
    case "forwards":
      c = b.child;
      for (e = null; null !== c; ) a = c.alternate, null !== a && null === Ch(a) && (e = c), c = c.sibling;
      c = e;
      null === c ? (e = b.child, b.child = null) : (e = c.sibling, c.sibling = null);
      wj(b, false, e, c, f2);
      break;
    case "backwards":
      c = null;
      e = b.child;
      for (b.child = null; null !== e; ) {
        a = e.alternate;
        if (null !== a && null === Ch(a)) {
          b.child = e;
          break;
        }
        a = e.sibling;
        e.sibling = c;
        c = e;
        e = a;
      }
      wj(b, true, c, null, f2);
      break;
    case "together":
      wj(b, false, null, null, void 0);
      break;
    default:
      b.memoizedState = null;
  }
  return b.child;
}
function ij(a, b) {
  0 === (b.mode & 1) && null !== a && (a.alternate = null, b.alternate = null, b.flags |= 2);
}
function Zi(a, b, c) {
  null !== a && (b.dependencies = a.dependencies);
  rh |= b.lanes;
  if (0 === (c & b.childLanes)) return null;
  if (null !== a && b.child !== a.child) throw Error(p(153));
  if (null !== b.child) {
    a = b.child;
    c = Pg(a, a.pendingProps);
    b.child = c;
    for (c.return = b; null !== a.sibling; ) a = a.sibling, c = c.sibling = Pg(a, a.pendingProps), c.return = b;
    c.sibling = null;
  }
  return b.child;
}
function yj(a, b, c) {
  switch (b.tag) {
    case 3:
      kj(b);
      Ig();
      break;
    case 5:
      Ah(b);
      break;
    case 1:
      Zf(b.type) && cg(b);
      break;
    case 4:
      yh(b, b.stateNode.containerInfo);
      break;
    case 10:
      var d = b.type._context, e = b.memoizedProps.value;
      G(Wg, d._currentValue);
      d._currentValue = e;
      break;
    case 13:
      d = b.memoizedState;
      if (null !== d) {
        if (null !== d.dehydrated) return G(L, L.current & 1), b.flags |= 128, null;
        if (0 !== (c & b.child.childLanes)) return oj(a, b, c);
        G(L, L.current & 1);
        a = Zi(a, b, c);
        return null !== a ? a.sibling : null;
      }
      G(L, L.current & 1);
      break;
    case 19:
      d = 0 !== (c & b.childLanes);
      if (0 !== (a.flags & 128)) {
        if (d) return xj(a, b, c);
        b.flags |= 128;
      }
      e = b.memoizedState;
      null !== e && (e.rendering = null, e.tail = null, e.lastEffect = null);
      G(L, L.current);
      if (d) break;
      else return null;
    case 22:
    case 23:
      return b.lanes = 0, dj(a, b, c);
  }
  return Zi(a, b, c);
}
var zj, Aj, Bj, Cj;
zj = function(a, b) {
  for (var c = b.child; null !== c; ) {
    if (5 === c.tag || 6 === c.tag) a.appendChild(c.stateNode);
    else if (4 !== c.tag && null !== c.child) {
      c.child.return = c;
      c = c.child;
      continue;
    }
    if (c === b) break;
    for (; null === c.sibling; ) {
      if (null === c.return || c.return === b) return;
      c = c.return;
    }
    c.sibling.return = c.return;
    c = c.sibling;
  }
};
Aj = function() {
};
Bj = function(a, b, c, d) {
  var e = a.memoizedProps;
  if (e !== d) {
    a = b.stateNode;
    xh(uh.current);
    var f2 = null;
    switch (c) {
      case "input":
        e = Ya(a, e);
        d = Ya(a, d);
        f2 = [];
        break;
      case "select":
        e = A({}, e, { value: void 0 });
        d = A({}, d, { value: void 0 });
        f2 = [];
        break;
      case "textarea":
        e = gb(a, e);
        d = gb(a, d);
        f2 = [];
        break;
      default:
        "function" !== typeof e.onClick && "function" === typeof d.onClick && (a.onclick = Bf);
    }
    ub(c, d);
    var g;
    c = null;
    for (l2 in e) if (!d.hasOwnProperty(l2) && e.hasOwnProperty(l2) && null != e[l2]) if ("style" === l2) {
      var h = e[l2];
      for (g in h) h.hasOwnProperty(g) && (c || (c = {}), c[g] = "");
    } else "dangerouslySetInnerHTML" !== l2 && "children" !== l2 && "suppressContentEditableWarning" !== l2 && "suppressHydrationWarning" !== l2 && "autoFocus" !== l2 && (ea.hasOwnProperty(l2) ? f2 || (f2 = []) : (f2 = f2 || []).push(l2, null));
    for (l2 in d) {
      var k2 = d[l2];
      h = null != e ? e[l2] : void 0;
      if (d.hasOwnProperty(l2) && k2 !== h && (null != k2 || null != h)) if ("style" === l2) if (h) {
        for (g in h) !h.hasOwnProperty(g) || k2 && k2.hasOwnProperty(g) || (c || (c = {}), c[g] = "");
        for (g in k2) k2.hasOwnProperty(g) && h[g] !== k2[g] && (c || (c = {}), c[g] = k2[g]);
      } else c || (f2 || (f2 = []), f2.push(
        l2,
        c
      )), c = k2;
      else "dangerouslySetInnerHTML" === l2 ? (k2 = k2 ? k2.__html : void 0, h = h ? h.__html : void 0, null != k2 && h !== k2 && (f2 = f2 || []).push(l2, k2)) : "children" === l2 ? "string" !== typeof k2 && "number" !== typeof k2 || (f2 = f2 || []).push(l2, "" + k2) : "suppressContentEditableWarning" !== l2 && "suppressHydrationWarning" !== l2 && (ea.hasOwnProperty(l2) ? (null != k2 && "onScroll" === l2 && D("scroll", a), f2 || h === k2 || (f2 = [])) : (f2 = f2 || []).push(l2, k2));
    }
    c && (f2 = f2 || []).push("style", c);
    var l2 = f2;
    if (b.updateQueue = l2) b.flags |= 4;
  }
};
Cj = function(a, b, c, d) {
  c !== d && (b.flags |= 4);
};
function Dj(a, b) {
  if (!I) switch (a.tailMode) {
    case "hidden":
      b = a.tail;
      for (var c = null; null !== b; ) null !== b.alternate && (c = b), b = b.sibling;
      null === c ? a.tail = null : c.sibling = null;
      break;
    case "collapsed":
      c = a.tail;
      for (var d = null; null !== c; ) null !== c.alternate && (d = c), c = c.sibling;
      null === d ? b || null === a.tail ? a.tail = null : a.tail.sibling = null : d.sibling = null;
  }
}
function S(a) {
  var b = null !== a.alternate && a.alternate.child === a.child, c = 0, d = 0;
  if (b) for (var e = a.child; null !== e; ) c |= e.lanes | e.childLanes, d |= e.subtreeFlags & 14680064, d |= e.flags & 14680064, e.return = a, e = e.sibling;
  else for (e = a.child; null !== e; ) c |= e.lanes | e.childLanes, d |= e.subtreeFlags, d |= e.flags, e.return = a, e = e.sibling;
  a.subtreeFlags |= d;
  a.childLanes = c;
  return b;
}
function Ej(a, b, c) {
  var d = b.pendingProps;
  wg(b);
  switch (b.tag) {
    case 2:
    case 16:
    case 15:
    case 0:
    case 11:
    case 7:
    case 8:
    case 12:
    case 9:
    case 14:
      return S(b), null;
    case 1:
      return Zf(b.type) && $f(), S(b), null;
    case 3:
      d = b.stateNode;
      zh();
      E(Wf);
      E(H);
      Eh();
      d.pendingContext && (d.context = d.pendingContext, d.pendingContext = null);
      if (null === a || null === a.child) Gg(b) ? b.flags |= 4 : null === a || a.memoizedState.isDehydrated && 0 === (b.flags & 256) || (b.flags |= 1024, null !== zg && (Fj(zg), zg = null));
      Aj(a, b);
      S(b);
      return null;
    case 5:
      Bh(b);
      var e = xh(wh.current);
      c = b.type;
      if (null !== a && null != b.stateNode) Bj(a, b, c, d, e), a.ref !== b.ref && (b.flags |= 512, b.flags |= 2097152);
      else {
        if (!d) {
          if (null === b.stateNode) throw Error(p(166));
          S(b);
          return null;
        }
        a = xh(uh.current);
        if (Gg(b)) {
          d = b.stateNode;
          c = b.type;
          var f2 = b.memoizedProps;
          d[Of] = b;
          d[Pf] = f2;
          a = 0 !== (b.mode & 1);
          switch (c) {
            case "dialog":
              D("cancel", d);
              D("close", d);
              break;
            case "iframe":
            case "object":
            case "embed":
              D("load", d);
              break;
            case "video":
            case "audio":
              for (e = 0; e < lf.length; e++) D(lf[e], d);
              break;
            case "source":
              D("error", d);
              break;
            case "img":
            case "image":
            case "link":
              D(
                "error",
                d
              );
              D("load", d);
              break;
            case "details":
              D("toggle", d);
              break;
            case "input":
              Za(d, f2);
              D("invalid", d);
              break;
            case "select":
              d._wrapperState = { wasMultiple: !!f2.multiple };
              D("invalid", d);
              break;
            case "textarea":
              hb(d, f2), D("invalid", d);
          }
          ub(c, f2);
          e = null;
          for (var g in f2) if (f2.hasOwnProperty(g)) {
            var h = f2[g];
            "children" === g ? "string" === typeof h ? d.textContent !== h && (true !== f2.suppressHydrationWarning && Af(d.textContent, h, a), e = ["children", h]) : "number" === typeof h && d.textContent !== "" + h && (true !== f2.suppressHydrationWarning && Af(
              d.textContent,
              h,
              a
            ), e = ["children", "" + h]) : ea.hasOwnProperty(g) && null != h && "onScroll" === g && D("scroll", d);
          }
          switch (c) {
            case "input":
              Va(d);
              db(d, f2, true);
              break;
            case "textarea":
              Va(d);
              jb(d);
              break;
            case "select":
            case "option":
              break;
            default:
              "function" === typeof f2.onClick && (d.onclick = Bf);
          }
          d = e;
          b.updateQueue = d;
          null !== d && (b.flags |= 4);
        } else {
          g = 9 === e.nodeType ? e : e.ownerDocument;
          "http://www.w3.org/1999/xhtml" === a && (a = kb(c));
          "http://www.w3.org/1999/xhtml" === a ? "script" === c ? (a = g.createElement("div"), a.innerHTML = "<script><\/script>", a = a.removeChild(a.firstChild)) : "string" === typeof d.is ? a = g.createElement(c, { is: d.is }) : (a = g.createElement(c), "select" === c && (g = a, d.multiple ? g.multiple = true : d.size && (g.size = d.size))) : a = g.createElementNS(a, c);
          a[Of] = b;
          a[Pf] = d;
          zj(a, b, false, false);
          b.stateNode = a;
          a: {
            g = vb(c, d);
            switch (c) {
              case "dialog":
                D("cancel", a);
                D("close", a);
                e = d;
                break;
              case "iframe":
              case "object":
              case "embed":
                D("load", a);
                e = d;
                break;
              case "video":
              case "audio":
                for (e = 0; e < lf.length; e++) D(lf[e], a);
                e = d;
                break;
              case "source":
                D("error", a);
                e = d;
                break;
              case "img":
              case "image":
              case "link":
                D(
                  "error",
                  a
                );
                D("load", a);
                e = d;
                break;
              case "details":
                D("toggle", a);
                e = d;
                break;
              case "input":
                Za(a, d);
                e = Ya(a, d);
                D("invalid", a);
                break;
              case "option":
                e = d;
                break;
              case "select":
                a._wrapperState = { wasMultiple: !!d.multiple };
                e = A({}, d, { value: void 0 });
                D("invalid", a);
                break;
              case "textarea":
                hb(a, d);
                e = gb(a, d);
                D("invalid", a);
                break;
              default:
                e = d;
            }
            ub(c, e);
            h = e;
            for (f2 in h) if (h.hasOwnProperty(f2)) {
              var k2 = h[f2];
              "style" === f2 ? sb(a, k2) : "dangerouslySetInnerHTML" === f2 ? (k2 = k2 ? k2.__html : void 0, null != k2 && nb(a, k2)) : "children" === f2 ? "string" === typeof k2 ? ("textarea" !== c || "" !== k2) && ob(a, k2) : "number" === typeof k2 && ob(a, "" + k2) : "suppressContentEditableWarning" !== f2 && "suppressHydrationWarning" !== f2 && "autoFocus" !== f2 && (ea.hasOwnProperty(f2) ? null != k2 && "onScroll" === f2 && D("scroll", a) : null != k2 && ta(a, f2, k2, g));
            }
            switch (c) {
              case "input":
                Va(a);
                db(a, d, false);
                break;
              case "textarea":
                Va(a);
                jb(a);
                break;
              case "option":
                null != d.value && a.setAttribute("value", "" + Sa(d.value));
                break;
              case "select":
                a.multiple = !!d.multiple;
                f2 = d.value;
                null != f2 ? fb(a, !!d.multiple, f2, false) : null != d.defaultValue && fb(
                  a,
                  !!d.multiple,
                  d.defaultValue,
                  true
                );
                break;
              default:
                "function" === typeof e.onClick && (a.onclick = Bf);
            }
            switch (c) {
              case "button":
              case "input":
              case "select":
              case "textarea":
                d = !!d.autoFocus;
                break a;
              case "img":
                d = true;
                break a;
              default:
                d = false;
            }
          }
          d && (b.flags |= 4);
        }
        null !== b.ref && (b.flags |= 512, b.flags |= 2097152);
      }
      S(b);
      return null;
    case 6:
      if (a && null != b.stateNode) Cj(a, b, a.memoizedProps, d);
      else {
        if ("string" !== typeof d && null === b.stateNode) throw Error(p(166));
        c = xh(wh.current);
        xh(uh.current);
        if (Gg(b)) {
          d = b.stateNode;
          c = b.memoizedProps;
          d[Of] = b;
          if (f2 = d.nodeValue !== c) {
            if (a = xg, null !== a) switch (a.tag) {
              case 3:
                Af(d.nodeValue, c, 0 !== (a.mode & 1));
                break;
              case 5:
                true !== a.memoizedProps.suppressHydrationWarning && Af(d.nodeValue, c, 0 !== (a.mode & 1));
            }
          }
          f2 && (b.flags |= 4);
        } else d = (9 === c.nodeType ? c : c.ownerDocument).createTextNode(d), d[Of] = b, b.stateNode = d;
      }
      S(b);
      return null;
    case 13:
      E(L);
      d = b.memoizedState;
      if (null === a || null !== a.memoizedState && null !== a.memoizedState.dehydrated) {
        if (I && null !== yg && 0 !== (b.mode & 1) && 0 === (b.flags & 128)) Hg(), Ig(), b.flags |= 98560, f2 = false;
        else if (f2 = Gg(b), null !== d && null !== d.dehydrated) {
          if (null === a) {
            if (!f2) throw Error(p(318));
            f2 = b.memoizedState;
            f2 = null !== f2 ? f2.dehydrated : null;
            if (!f2) throw Error(p(317));
            f2[Of] = b;
          } else Ig(), 0 === (b.flags & 128) && (b.memoizedState = null), b.flags |= 4;
          S(b);
          f2 = false;
        } else null !== zg && (Fj(zg), zg = null), f2 = true;
        if (!f2) return b.flags & 65536 ? b : null;
      }
      if (0 !== (b.flags & 128)) return b.lanes = c, b;
      d = null !== d;
      d !== (null !== a && null !== a.memoizedState) && d && (b.child.flags |= 8192, 0 !== (b.mode & 1) && (null === a || 0 !== (L.current & 1) ? 0 === T && (T = 3) : tj()));
      null !== b.updateQueue && (b.flags |= 4);
      S(b);
      return null;
    case 4:
      return zh(), Aj(a, b), null === a && sf(b.stateNode.containerInfo), S(b), null;
    case 10:
      return ah(b.type._context), S(b), null;
    case 17:
      return Zf(b.type) && $f(), S(b), null;
    case 19:
      E(L);
      f2 = b.memoizedState;
      if (null === f2) return S(b), null;
      d = 0 !== (b.flags & 128);
      g = f2.rendering;
      if (null === g) if (d) Dj(f2, false);
      else {
        if (0 !== T || null !== a && 0 !== (a.flags & 128)) for (a = b.child; null !== a; ) {
          g = Ch(a);
          if (null !== g) {
            b.flags |= 128;
            Dj(f2, false);
            d = g.updateQueue;
            null !== d && (b.updateQueue = d, b.flags |= 4);
            b.subtreeFlags = 0;
            d = c;
            for (c = b.child; null !== c; ) f2 = c, a = d, f2.flags &= 14680066, g = f2.alternate, null === g ? (f2.childLanes = 0, f2.lanes = a, f2.child = null, f2.subtreeFlags = 0, f2.memoizedProps = null, f2.memoizedState = null, f2.updateQueue = null, f2.dependencies = null, f2.stateNode = null) : (f2.childLanes = g.childLanes, f2.lanes = g.lanes, f2.child = g.child, f2.subtreeFlags = 0, f2.deletions = null, f2.memoizedProps = g.memoizedProps, f2.memoizedState = g.memoizedState, f2.updateQueue = g.updateQueue, f2.type = g.type, a = g.dependencies, f2.dependencies = null === a ? null : { lanes: a.lanes, firstContext: a.firstContext }), c = c.sibling;
            G(L, L.current & 1 | 2);
            return b.child;
          }
          a = a.sibling;
        }
        null !== f2.tail && B() > Gj && (b.flags |= 128, d = true, Dj(f2, false), b.lanes = 4194304);
      }
      else {
        if (!d) if (a = Ch(g), null !== a) {
          if (b.flags |= 128, d = true, c = a.updateQueue, null !== c && (b.updateQueue = c, b.flags |= 4), Dj(f2, true), null === f2.tail && "hidden" === f2.tailMode && !g.alternate && !I) return S(b), null;
        } else 2 * B() - f2.renderingStartTime > Gj && 1073741824 !== c && (b.flags |= 128, d = true, Dj(f2, false), b.lanes = 4194304);
        f2.isBackwards ? (g.sibling = b.child, b.child = g) : (c = f2.last, null !== c ? c.sibling = g : b.child = g, f2.last = g);
      }
      if (null !== f2.tail) return b = f2.tail, f2.rendering = b, f2.tail = b.sibling, f2.renderingStartTime = B(), b.sibling = null, c = L.current, G(L, d ? c & 1 | 2 : c & 1), b;
      S(b);
      return null;
    case 22:
    case 23:
      return Hj(), d = null !== b.memoizedState, null !== a && null !== a.memoizedState !== d && (b.flags |= 8192), d && 0 !== (b.mode & 1) ? 0 !== (fj & 1073741824) && (S(b), b.subtreeFlags & 6 && (b.flags |= 8192)) : S(b), null;
    case 24:
      return null;
    case 25:
      return null;
  }
  throw Error(p(156, b.tag));
}
function Ij(a, b) {
  wg(b);
  switch (b.tag) {
    case 1:
      return Zf(b.type) && $f(), a = b.flags, a & 65536 ? (b.flags = a & -65537 | 128, b) : null;
    case 3:
      return zh(), E(Wf), E(H), Eh(), a = b.flags, 0 !== (a & 65536) && 0 === (a & 128) ? (b.flags = a & -65537 | 128, b) : null;
    case 5:
      return Bh(b), null;
    case 13:
      E(L);
      a = b.memoizedState;
      if (null !== a && null !== a.dehydrated) {
        if (null === b.alternate) throw Error(p(340));
        Ig();
      }
      a = b.flags;
      return a & 65536 ? (b.flags = a & -65537 | 128, b) : null;
    case 19:
      return E(L), null;
    case 4:
      return zh(), null;
    case 10:
      return ah(b.type._context), null;
    case 22:
    case 23:
      return Hj(), null;
    case 24:
      return null;
    default:
      return null;
  }
}
var Jj = false, U = false, Kj = "function" === typeof WeakSet ? WeakSet : Set, V = null;
function Lj(a, b) {
  var c = a.ref;
  if (null !== c) if ("function" === typeof c) try {
    c(null);
  } catch (d) {
    W(a, b, d);
  }
  else c.current = null;
}
function Mj(a, b, c) {
  try {
    c();
  } catch (d) {
    W(a, b, d);
  }
}
var Nj = false;
function Oj(a, b) {
  Cf = dd;
  a = Me();
  if (Ne(a)) {
    if ("selectionStart" in a) var c = { start: a.selectionStart, end: a.selectionEnd };
    else a: {
      c = (c = a.ownerDocument) && c.defaultView || window;
      var d = c.getSelection && c.getSelection();
      if (d && 0 !== d.rangeCount) {
        c = d.anchorNode;
        var e = d.anchorOffset, f2 = d.focusNode;
        d = d.focusOffset;
        try {
          c.nodeType, f2.nodeType;
        } catch (F2) {
          c = null;
          break a;
        }
        var g = 0, h = -1, k2 = -1, l2 = 0, m2 = 0, q2 = a, r2 = null;
        b: for (; ; ) {
          for (var y2; ; ) {
            q2 !== c || 0 !== e && 3 !== q2.nodeType || (h = g + e);
            q2 !== f2 || 0 !== d && 3 !== q2.nodeType || (k2 = g + d);
            3 === q2.nodeType && (g += q2.nodeValue.length);
            if (null === (y2 = q2.firstChild)) break;
            r2 = q2;
            q2 = y2;
          }
          for (; ; ) {
            if (q2 === a) break b;
            r2 === c && ++l2 === e && (h = g);
            r2 === f2 && ++m2 === d && (k2 = g);
            if (null !== (y2 = q2.nextSibling)) break;
            q2 = r2;
            r2 = q2.parentNode;
          }
          q2 = y2;
        }
        c = -1 === h || -1 === k2 ? null : { start: h, end: k2 };
      } else c = null;
    }
    c = c || { start: 0, end: 0 };
  } else c = null;
  Df = { focusedElem: a, selectionRange: c };
  dd = false;
  for (V = b; null !== V; ) if (b = V, a = b.child, 0 !== (b.subtreeFlags & 1028) && null !== a) a.return = b, V = a;
  else for (; null !== V; ) {
    b = V;
    try {
      var n2 = b.alternate;
      if (0 !== (b.flags & 1024)) switch (b.tag) {
        case 0:
        case 11:
        case 15:
          break;
        case 1:
          if (null !== n2) {
            var t2 = n2.memoizedProps, J2 = n2.memoizedState, x2 = b.stateNode, w2 = x2.getSnapshotBeforeUpdate(b.elementType === b.type ? t2 : Ci(b.type, t2), J2);
            x2.__reactInternalSnapshotBeforeUpdate = w2;
          }
          break;
        case 3:
          var u2 = b.stateNode.containerInfo;
          1 === u2.nodeType ? u2.textContent = "" : 9 === u2.nodeType && u2.documentElement && u2.removeChild(u2.documentElement);
          break;
        case 5:
        case 6:
        case 4:
        case 17:
          break;
        default:
          throw Error(p(163));
      }
    } catch (F2) {
      W(b, b.return, F2);
    }
    a = b.sibling;
    if (null !== a) {
      a.return = b.return;
      V = a;
      break;
    }
    V = b.return;
  }
  n2 = Nj;
  Nj = false;
  return n2;
}
function Pj(a, b, c) {
  var d = b.updateQueue;
  d = null !== d ? d.lastEffect : null;
  if (null !== d) {
    var e = d = d.next;
    do {
      if ((e.tag & a) === a) {
        var f2 = e.destroy;
        e.destroy = void 0;
        void 0 !== f2 && Mj(b, c, f2);
      }
      e = e.next;
    } while (e !== d);
  }
}
function Qj(a, b) {
  b = b.updateQueue;
  b = null !== b ? b.lastEffect : null;
  if (null !== b) {
    var c = b = b.next;
    do {
      if ((c.tag & a) === a) {
        var d = c.create;
        c.destroy = d();
      }
      c = c.next;
    } while (c !== b);
  }
}
function Rj(a) {
  var b = a.ref;
  if (null !== b) {
    var c = a.stateNode;
    switch (a.tag) {
      case 5:
        a = c;
        break;
      default:
        a = c;
    }
    "function" === typeof b ? b(a) : b.current = a;
  }
}
function Sj(a) {
  var b = a.alternate;
  null !== b && (a.alternate = null, Sj(b));
  a.child = null;
  a.deletions = null;
  a.sibling = null;
  5 === a.tag && (b = a.stateNode, null !== b && (delete b[Of], delete b[Pf], delete b[of], delete b[Qf], delete b[Rf]));
  a.stateNode = null;
  a.return = null;
  a.dependencies = null;
  a.memoizedProps = null;
  a.memoizedState = null;
  a.pendingProps = null;
  a.stateNode = null;
  a.updateQueue = null;
}
function Tj(a) {
  return 5 === a.tag || 3 === a.tag || 4 === a.tag;
}
function Uj(a) {
  a: for (; ; ) {
    for (; null === a.sibling; ) {
      if (null === a.return || Tj(a.return)) return null;
      a = a.return;
    }
    a.sibling.return = a.return;
    for (a = a.sibling; 5 !== a.tag && 6 !== a.tag && 18 !== a.tag; ) {
      if (a.flags & 2) continue a;
      if (null === a.child || 4 === a.tag) continue a;
      else a.child.return = a, a = a.child;
    }
    if (!(a.flags & 2)) return a.stateNode;
  }
}
function Vj(a, b, c) {
  var d = a.tag;
  if (5 === d || 6 === d) a = a.stateNode, b ? 8 === c.nodeType ? c.parentNode.insertBefore(a, b) : c.insertBefore(a, b) : (8 === c.nodeType ? (b = c.parentNode, b.insertBefore(a, c)) : (b = c, b.appendChild(a)), c = c._reactRootContainer, null !== c && void 0 !== c || null !== b.onclick || (b.onclick = Bf));
  else if (4 !== d && (a = a.child, null !== a)) for (Vj(a, b, c), a = a.sibling; null !== a; ) Vj(a, b, c), a = a.sibling;
}
function Wj(a, b, c) {
  var d = a.tag;
  if (5 === d || 6 === d) a = a.stateNode, b ? c.insertBefore(a, b) : c.appendChild(a);
  else if (4 !== d && (a = a.child, null !== a)) for (Wj(a, b, c), a = a.sibling; null !== a; ) Wj(a, b, c), a = a.sibling;
}
var X$1 = null, Xj = false;
function Yj(a, b, c) {
  for (c = c.child; null !== c; ) Zj(a, b, c), c = c.sibling;
}
function Zj(a, b, c) {
  if (lc && "function" === typeof lc.onCommitFiberUnmount) try {
    lc.onCommitFiberUnmount(kc, c);
  } catch (h) {
  }
  switch (c.tag) {
    case 5:
      U || Lj(c, b);
    case 6:
      var d = X$1, e = Xj;
      X$1 = null;
      Yj(a, b, c);
      X$1 = d;
      Xj = e;
      null !== X$1 && (Xj ? (a = X$1, c = c.stateNode, 8 === a.nodeType ? a.parentNode.removeChild(c) : a.removeChild(c)) : X$1.removeChild(c.stateNode));
      break;
    case 18:
      null !== X$1 && (Xj ? (a = X$1, c = c.stateNode, 8 === a.nodeType ? Kf(a.parentNode, c) : 1 === a.nodeType && Kf(a, c), bd(a)) : Kf(X$1, c.stateNode));
      break;
    case 4:
      d = X$1;
      e = Xj;
      X$1 = c.stateNode.containerInfo;
      Xj = true;
      Yj(a, b, c);
      X$1 = d;
      Xj = e;
      break;
    case 0:
    case 11:
    case 14:
    case 15:
      if (!U && (d = c.updateQueue, null !== d && (d = d.lastEffect, null !== d))) {
        e = d = d.next;
        do {
          var f2 = e, g = f2.destroy;
          f2 = f2.tag;
          void 0 !== g && (0 !== (f2 & 2) ? Mj(c, b, g) : 0 !== (f2 & 4) && Mj(c, b, g));
          e = e.next;
        } while (e !== d);
      }
      Yj(a, b, c);
      break;
    case 1:
      if (!U && (Lj(c, b), d = c.stateNode, "function" === typeof d.componentWillUnmount)) try {
        d.props = c.memoizedProps, d.state = c.memoizedState, d.componentWillUnmount();
      } catch (h) {
        W(c, b, h);
      }
      Yj(a, b, c);
      break;
    case 21:
      Yj(a, b, c);
      break;
    case 22:
      c.mode & 1 ? (U = (d = U) || null !== c.memoizedState, Yj(a, b, c), U = d) : Yj(a, b, c);
      break;
    default:
      Yj(a, b, c);
  }
}
function ak(a) {
  var b = a.updateQueue;
  if (null !== b) {
    a.updateQueue = null;
    var c = a.stateNode;
    null === c && (c = a.stateNode = new Kj());
    b.forEach(function(b2) {
      var d = bk.bind(null, a, b2);
      c.has(b2) || (c.add(b2), b2.then(d, d));
    });
  }
}
function ck(a, b) {
  var c = b.deletions;
  if (null !== c) for (var d = 0; d < c.length; d++) {
    var e = c[d];
    try {
      var f2 = a, g = b, h = g;
      a: for (; null !== h; ) {
        switch (h.tag) {
          case 5:
            X$1 = h.stateNode;
            Xj = false;
            break a;
          case 3:
            X$1 = h.stateNode.containerInfo;
            Xj = true;
            break a;
          case 4:
            X$1 = h.stateNode.containerInfo;
            Xj = true;
            break a;
        }
        h = h.return;
      }
      if (null === X$1) throw Error(p(160));
      Zj(f2, g, e);
      X$1 = null;
      Xj = false;
      var k2 = e.alternate;
      null !== k2 && (k2.return = null);
      e.return = null;
    } catch (l2) {
      W(e, b, l2);
    }
  }
  if (b.subtreeFlags & 12854) for (b = b.child; null !== b; ) dk(b, a), b = b.sibling;
}
function dk(a, b) {
  var c = a.alternate, d = a.flags;
  switch (a.tag) {
    case 0:
    case 11:
    case 14:
    case 15:
      ck(b, a);
      ek(a);
      if (d & 4) {
        try {
          Pj(3, a, a.return), Qj(3, a);
        } catch (t2) {
          W(a, a.return, t2);
        }
        try {
          Pj(5, a, a.return);
        } catch (t2) {
          W(a, a.return, t2);
        }
      }
      break;
    case 1:
      ck(b, a);
      ek(a);
      d & 512 && null !== c && Lj(c, c.return);
      break;
    case 5:
      ck(b, a);
      ek(a);
      d & 512 && null !== c && Lj(c, c.return);
      if (a.flags & 32) {
        var e = a.stateNode;
        try {
          ob(e, "");
        } catch (t2) {
          W(a, a.return, t2);
        }
      }
      if (d & 4 && (e = a.stateNode, null != e)) {
        var f2 = a.memoizedProps, g = null !== c ? c.memoizedProps : f2, h = a.type, k2 = a.updateQueue;
        a.updateQueue = null;
        if (null !== k2) try {
          "input" === h && "radio" === f2.type && null != f2.name && ab(e, f2);
          vb(h, g);
          var l2 = vb(h, f2);
          for (g = 0; g < k2.length; g += 2) {
            var m2 = k2[g], q2 = k2[g + 1];
            "style" === m2 ? sb(e, q2) : "dangerouslySetInnerHTML" === m2 ? nb(e, q2) : "children" === m2 ? ob(e, q2) : ta(e, m2, q2, l2);
          }
          switch (h) {
            case "input":
              bb(e, f2);
              break;
            case "textarea":
              ib(e, f2);
              break;
            case "select":
              var r2 = e._wrapperState.wasMultiple;
              e._wrapperState.wasMultiple = !!f2.multiple;
              var y2 = f2.value;
              null != y2 ? fb(e, !!f2.multiple, y2, false) : r2 !== !!f2.multiple && (null != f2.defaultValue ? fb(
                e,
                !!f2.multiple,
                f2.defaultValue,
                true
              ) : fb(e, !!f2.multiple, f2.multiple ? [] : "", false));
          }
          e[Pf] = f2;
        } catch (t2) {
          W(a, a.return, t2);
        }
      }
      break;
    case 6:
      ck(b, a);
      ek(a);
      if (d & 4) {
        if (null === a.stateNode) throw Error(p(162));
        e = a.stateNode;
        f2 = a.memoizedProps;
        try {
          e.nodeValue = f2;
        } catch (t2) {
          W(a, a.return, t2);
        }
      }
      break;
    case 3:
      ck(b, a);
      ek(a);
      if (d & 4 && null !== c && c.memoizedState.isDehydrated) try {
        bd(b.containerInfo);
      } catch (t2) {
        W(a, a.return, t2);
      }
      break;
    case 4:
      ck(b, a);
      ek(a);
      break;
    case 13:
      ck(b, a);
      ek(a);
      e = a.child;
      e.flags & 8192 && (f2 = null !== e.memoizedState, e.stateNode.isHidden = f2, !f2 || null !== e.alternate && null !== e.alternate.memoizedState || (fk = B()));
      d & 4 && ak(a);
      break;
    case 22:
      m2 = null !== c && null !== c.memoizedState;
      a.mode & 1 ? (U = (l2 = U) || m2, ck(b, a), U = l2) : ck(b, a);
      ek(a);
      if (d & 8192) {
        l2 = null !== a.memoizedState;
        if ((a.stateNode.isHidden = l2) && !m2 && 0 !== (a.mode & 1)) for (V = a, m2 = a.child; null !== m2; ) {
          for (q2 = V = m2; null !== V; ) {
            r2 = V;
            y2 = r2.child;
            switch (r2.tag) {
              case 0:
              case 11:
              case 14:
              case 15:
                Pj(4, r2, r2.return);
                break;
              case 1:
                Lj(r2, r2.return);
                var n2 = r2.stateNode;
                if ("function" === typeof n2.componentWillUnmount) {
                  d = r2;
                  c = r2.return;
                  try {
                    b = d, n2.props = b.memoizedProps, n2.state = b.memoizedState, n2.componentWillUnmount();
                  } catch (t2) {
                    W(d, c, t2);
                  }
                }
                break;
              case 5:
                Lj(r2, r2.return);
                break;
              case 22:
                if (null !== r2.memoizedState) {
                  gk(q2);
                  continue;
                }
            }
            null !== y2 ? (y2.return = r2, V = y2) : gk(q2);
          }
          m2 = m2.sibling;
        }
        a: for (m2 = null, q2 = a; ; ) {
          if (5 === q2.tag) {
            if (null === m2) {
              m2 = q2;
              try {
                e = q2.stateNode, l2 ? (f2 = e.style, "function" === typeof f2.setProperty ? f2.setProperty("display", "none", "important") : f2.display = "none") : (h = q2.stateNode, k2 = q2.memoizedProps.style, g = void 0 !== k2 && null !== k2 && k2.hasOwnProperty("display") ? k2.display : null, h.style.display = rb("display", g));
              } catch (t2) {
                W(a, a.return, t2);
              }
            }
          } else if (6 === q2.tag) {
            if (null === m2) try {
              q2.stateNode.nodeValue = l2 ? "" : q2.memoizedProps;
            } catch (t2) {
              W(a, a.return, t2);
            }
          } else if ((22 !== q2.tag && 23 !== q2.tag || null === q2.memoizedState || q2 === a) && null !== q2.child) {
            q2.child.return = q2;
            q2 = q2.child;
            continue;
          }
          if (q2 === a) break a;
          for (; null === q2.sibling; ) {
            if (null === q2.return || q2.return === a) break a;
            m2 === q2 && (m2 = null);
            q2 = q2.return;
          }
          m2 === q2 && (m2 = null);
          q2.sibling.return = q2.return;
          q2 = q2.sibling;
        }
      }
      break;
    case 19:
      ck(b, a);
      ek(a);
      d & 4 && ak(a);
      break;
    case 21:
      break;
    default:
      ck(
        b,
        a
      ), ek(a);
  }
}
function ek(a) {
  var b = a.flags;
  if (b & 2) {
    try {
      a: {
        for (var c = a.return; null !== c; ) {
          if (Tj(c)) {
            var d = c;
            break a;
          }
          c = c.return;
        }
        throw Error(p(160));
      }
      switch (d.tag) {
        case 5:
          var e = d.stateNode;
          d.flags & 32 && (ob(e, ""), d.flags &= -33);
          var f2 = Uj(a);
          Wj(a, f2, e);
          break;
        case 3:
        case 4:
          var g = d.stateNode.containerInfo, h = Uj(a);
          Vj(a, h, g);
          break;
        default:
          throw Error(p(161));
      }
    } catch (k2) {
      W(a, a.return, k2);
    }
    a.flags &= -3;
  }
  b & 4096 && (a.flags &= -4097);
}
function hk(a, b, c) {
  V = a;
  ik(a);
}
function ik(a, b, c) {
  for (var d = 0 !== (a.mode & 1); null !== V; ) {
    var e = V, f2 = e.child;
    if (22 === e.tag && d) {
      var g = null !== e.memoizedState || Jj;
      if (!g) {
        var h = e.alternate, k2 = null !== h && null !== h.memoizedState || U;
        h = Jj;
        var l2 = U;
        Jj = g;
        if ((U = k2) && !l2) for (V = e; null !== V; ) g = V, k2 = g.child, 22 === g.tag && null !== g.memoizedState ? jk(e) : null !== k2 ? (k2.return = g, V = k2) : jk(e);
        for (; null !== f2; ) V = f2, ik(f2), f2 = f2.sibling;
        V = e;
        Jj = h;
        U = l2;
      }
      kk(a);
    } else 0 !== (e.subtreeFlags & 8772) && null !== f2 ? (f2.return = e, V = f2) : kk(a);
  }
}
function kk(a) {
  for (; null !== V; ) {
    var b = V;
    if (0 !== (b.flags & 8772)) {
      var c = b.alternate;
      try {
        if (0 !== (b.flags & 8772)) switch (b.tag) {
          case 0:
          case 11:
          case 15:
            U || Qj(5, b);
            break;
          case 1:
            var d = b.stateNode;
            if (b.flags & 4 && !U) if (null === c) d.componentDidMount();
            else {
              var e = b.elementType === b.type ? c.memoizedProps : Ci(b.type, c.memoizedProps);
              d.componentDidUpdate(e, c.memoizedState, d.__reactInternalSnapshotBeforeUpdate);
            }
            var f2 = b.updateQueue;
            null !== f2 && sh(b, f2, d);
            break;
          case 3:
            var g = b.updateQueue;
            if (null !== g) {
              c = null;
              if (null !== b.child) switch (b.child.tag) {
                case 5:
                  c = b.child.stateNode;
                  break;
                case 1:
                  c = b.child.stateNode;
              }
              sh(b, g, c);
            }
            break;
          case 5:
            var h = b.stateNode;
            if (null === c && b.flags & 4) {
              c = h;
              var k2 = b.memoizedProps;
              switch (b.type) {
                case "button":
                case "input":
                case "select":
                case "textarea":
                  k2.autoFocus && c.focus();
                  break;
                case "img":
                  k2.src && (c.src = k2.src);
              }
            }
            break;
          case 6:
            break;
          case 4:
            break;
          case 12:
            break;
          case 13:
            if (null === b.memoizedState) {
              var l2 = b.alternate;
              if (null !== l2) {
                var m2 = l2.memoizedState;
                if (null !== m2) {
                  var q2 = m2.dehydrated;
                  null !== q2 && bd(q2);
                }
              }
            }
            break;
          case 19:
          case 17:
          case 21:
          case 22:
          case 23:
          case 25:
            break;
          default:
            throw Error(p(163));
        }
        U || b.flags & 512 && Rj(b);
      } catch (r2) {
        W(b, b.return, r2);
      }
    }
    if (b === a) {
      V = null;
      break;
    }
    c = b.sibling;
    if (null !== c) {
      c.return = b.return;
      V = c;
      break;
    }
    V = b.return;
  }
}
function gk(a) {
  for (; null !== V; ) {
    var b = V;
    if (b === a) {
      V = null;
      break;
    }
    var c = b.sibling;
    if (null !== c) {
      c.return = b.return;
      V = c;
      break;
    }
    V = b.return;
  }
}
function jk(a) {
  for (; null !== V; ) {
    var b = V;
    try {
      switch (b.tag) {
        case 0:
        case 11:
        case 15:
          var c = b.return;
          try {
            Qj(4, b);
          } catch (k2) {
            W(b, c, k2);
          }
          break;
        case 1:
          var d = b.stateNode;
          if ("function" === typeof d.componentDidMount) {
            var e = b.return;
            try {
              d.componentDidMount();
            } catch (k2) {
              W(b, e, k2);
            }
          }
          var f2 = b.return;
          try {
            Rj(b);
          } catch (k2) {
            W(b, f2, k2);
          }
          break;
        case 5:
          var g = b.return;
          try {
            Rj(b);
          } catch (k2) {
            W(b, g, k2);
          }
      }
    } catch (k2) {
      W(b, b.return, k2);
    }
    if (b === a) {
      V = null;
      break;
    }
    var h = b.sibling;
    if (null !== h) {
      h.return = b.return;
      V = h;
      break;
    }
    V = b.return;
  }
}
var lk = Math.ceil, mk = ua.ReactCurrentDispatcher, nk = ua.ReactCurrentOwner, ok = ua.ReactCurrentBatchConfig, K = 0, Q = null, Y = null, Z = 0, fj = 0, ej = Uf(0), T = 0, pk = null, rh = 0, qk = 0, rk = 0, sk = null, tk = null, fk = 0, Gj = Infinity, uk = null, Oi = false, Pi = null, Ri = null, vk = false, wk = null, xk = 0, yk = 0, zk = null, Ak = -1, Bk = 0;
function R() {
  return 0 !== (K & 6) ? B() : -1 !== Ak ? Ak : Ak = B();
}
function yi(a) {
  if (0 === (a.mode & 1)) return 1;
  if (0 !== (K & 2) && 0 !== Z) return Z & -Z;
  if (null !== Kg.transition) return 0 === Bk && (Bk = yc()), Bk;
  a = C;
  if (0 !== a) return a;
  a = window.event;
  a = void 0 === a ? 16 : jd(a.type);
  return a;
}
function gi(a, b, c, d) {
  if (50 < yk) throw yk = 0, zk = null, Error(p(185));
  Ac(a, c, d);
  if (0 === (K & 2) || a !== Q) a === Q && (0 === (K & 2) && (qk |= c), 4 === T && Ck(a, Z)), Dk(a, d), 1 === c && 0 === K && 0 === (b.mode & 1) && (Gj = B() + 500, fg && jg());
}
function Dk(a, b) {
  var c = a.callbackNode;
  wc(a, b);
  var d = uc(a, a === Q ? Z : 0);
  if (0 === d) null !== c && bc(c), a.callbackNode = null, a.callbackPriority = 0;
  else if (b = d & -d, a.callbackPriority !== b) {
    null != c && bc(c);
    if (1 === b) 0 === a.tag ? ig(Ek.bind(null, a)) : hg(Ek.bind(null, a)), Jf(function() {
      0 === (K & 6) && jg();
    }), c = null;
    else {
      switch (Dc(d)) {
        case 1:
          c = fc;
          break;
        case 4:
          c = gc;
          break;
        case 16:
          c = hc;
          break;
        case 536870912:
          c = jc;
          break;
        default:
          c = hc;
      }
      c = Fk(c, Gk.bind(null, a));
    }
    a.callbackPriority = b;
    a.callbackNode = c;
  }
}
function Gk(a, b) {
  Ak = -1;
  Bk = 0;
  if (0 !== (K & 6)) throw Error(p(327));
  var c = a.callbackNode;
  if (Hk() && a.callbackNode !== c) return null;
  var d = uc(a, a === Q ? Z : 0);
  if (0 === d) return null;
  if (0 !== (d & 30) || 0 !== (d & a.expiredLanes) || b) b = Ik(a, d);
  else {
    b = d;
    var e = K;
    K |= 2;
    var f2 = Jk();
    if (Q !== a || Z !== b) uk = null, Gj = B() + 500, Kk(a, b);
    do
      try {
        Lk();
        break;
      } catch (h) {
        Mk(a, h);
      }
    while (1);
    $g();
    mk.current = f2;
    K = e;
    null !== Y ? b = 0 : (Q = null, Z = 0, b = T);
  }
  if (0 !== b) {
    2 === b && (e = xc(a), 0 !== e && (d = e, b = Nk(a, e)));
    if (1 === b) throw c = pk, Kk(a, 0), Ck(a, d), Dk(a, B()), c;
    if (6 === b) Ck(a, d);
    else {
      e = a.current.alternate;
      if (0 === (d & 30) && !Ok(e) && (b = Ik(a, d), 2 === b && (f2 = xc(a), 0 !== f2 && (d = f2, b = Nk(a, f2))), 1 === b)) throw c = pk, Kk(a, 0), Ck(a, d), Dk(a, B()), c;
      a.finishedWork = e;
      a.finishedLanes = d;
      switch (b) {
        case 0:
        case 1:
          throw Error(p(345));
        case 2:
          Pk(a, tk, uk);
          break;
        case 3:
          Ck(a, d);
          if ((d & 130023424) === d && (b = fk + 500 - B(), 10 < b)) {
            if (0 !== uc(a, 0)) break;
            e = a.suspendedLanes;
            if ((e & d) !== d) {
              R();
              a.pingedLanes |= a.suspendedLanes & e;
              break;
            }
            a.timeoutHandle = Ff(Pk.bind(null, a, tk, uk), b);
            break;
          }
          Pk(a, tk, uk);
          break;
        case 4:
          Ck(a, d);
          if ((d & 4194240) === d) break;
          b = a.eventTimes;
          for (e = -1; 0 < d; ) {
            var g = 31 - oc(d);
            f2 = 1 << g;
            g = b[g];
            g > e && (e = g);
            d &= ~f2;
          }
          d = e;
          d = B() - d;
          d = (120 > d ? 120 : 480 > d ? 480 : 1080 > d ? 1080 : 1920 > d ? 1920 : 3e3 > d ? 3e3 : 4320 > d ? 4320 : 1960 * lk(d / 1960)) - d;
          if (10 < d) {
            a.timeoutHandle = Ff(Pk.bind(null, a, tk, uk), d);
            break;
          }
          Pk(a, tk, uk);
          break;
        case 5:
          Pk(a, tk, uk);
          break;
        default:
          throw Error(p(329));
      }
    }
  }
  Dk(a, B());
  return a.callbackNode === c ? Gk.bind(null, a) : null;
}
function Nk(a, b) {
  var c = sk;
  a.current.memoizedState.isDehydrated && (Kk(a, b).flags |= 256);
  a = Ik(a, b);
  2 !== a && (b = tk, tk = c, null !== b && Fj(b));
  return a;
}
function Fj(a) {
  null === tk ? tk = a : tk.push.apply(tk, a);
}
function Ok(a) {
  for (var b = a; ; ) {
    if (b.flags & 16384) {
      var c = b.updateQueue;
      if (null !== c && (c = c.stores, null !== c)) for (var d = 0; d < c.length; d++) {
        var e = c[d], f2 = e.getSnapshot;
        e = e.value;
        try {
          if (!He(f2(), e)) return false;
        } catch (g) {
          return false;
        }
      }
    }
    c = b.child;
    if (b.subtreeFlags & 16384 && null !== c) c.return = b, b = c;
    else {
      if (b === a) break;
      for (; null === b.sibling; ) {
        if (null === b.return || b.return === a) return true;
        b = b.return;
      }
      b.sibling.return = b.return;
      b = b.sibling;
    }
  }
  return true;
}
function Ck(a, b) {
  b &= ~rk;
  b &= ~qk;
  a.suspendedLanes |= b;
  a.pingedLanes &= ~b;
  for (a = a.expirationTimes; 0 < b; ) {
    var c = 31 - oc(b), d = 1 << c;
    a[c] = -1;
    b &= ~d;
  }
}
function Ek(a) {
  if (0 !== (K & 6)) throw Error(p(327));
  Hk();
  var b = uc(a, 0);
  if (0 === (b & 1)) return Dk(a, B()), null;
  var c = Ik(a, b);
  if (0 !== a.tag && 2 === c) {
    var d = xc(a);
    0 !== d && (b = d, c = Nk(a, d));
  }
  if (1 === c) throw c = pk, Kk(a, 0), Ck(a, b), Dk(a, B()), c;
  if (6 === c) throw Error(p(345));
  a.finishedWork = a.current.alternate;
  a.finishedLanes = b;
  Pk(a, tk, uk);
  Dk(a, B());
  return null;
}
function Qk(a, b) {
  var c = K;
  K |= 1;
  try {
    return a(b);
  } finally {
    K = c, 0 === K && (Gj = B() + 500, fg && jg());
  }
}
function Rk(a) {
  null !== wk && 0 === wk.tag && 0 === (K & 6) && Hk();
  var b = K;
  K |= 1;
  var c = ok.transition, d = C;
  try {
    if (ok.transition = null, C = 1, a) return a();
  } finally {
    C = d, ok.transition = c, K = b, 0 === (K & 6) && jg();
  }
}
function Hj() {
  fj = ej.current;
  E(ej);
}
function Kk(a, b) {
  a.finishedWork = null;
  a.finishedLanes = 0;
  var c = a.timeoutHandle;
  -1 !== c && (a.timeoutHandle = -1, Gf(c));
  if (null !== Y) for (c = Y.return; null !== c; ) {
    var d = c;
    wg(d);
    switch (d.tag) {
      case 1:
        d = d.type.childContextTypes;
        null !== d && void 0 !== d && $f();
        break;
      case 3:
        zh();
        E(Wf);
        E(H);
        Eh();
        break;
      case 5:
        Bh(d);
        break;
      case 4:
        zh();
        break;
      case 13:
        E(L);
        break;
      case 19:
        E(L);
        break;
      case 10:
        ah(d.type._context);
        break;
      case 22:
      case 23:
        Hj();
    }
    c = c.return;
  }
  Q = a;
  Y = a = Pg(a.current, null);
  Z = fj = b;
  T = 0;
  pk = null;
  rk = qk = rh = 0;
  tk = sk = null;
  if (null !== fh) {
    for (b = 0; b < fh.length; b++) if (c = fh[b], d = c.interleaved, null !== d) {
      c.interleaved = null;
      var e = d.next, f2 = c.pending;
      if (null !== f2) {
        var g = f2.next;
        f2.next = e;
        d.next = g;
      }
      c.pending = d;
    }
    fh = null;
  }
  return a;
}
function Mk(a, b) {
  do {
    var c = Y;
    try {
      $g();
      Fh.current = Rh;
      if (Ih) {
        for (var d = M.memoizedState; null !== d; ) {
          var e = d.queue;
          null !== e && (e.pending = null);
          d = d.next;
        }
        Ih = false;
      }
      Hh = 0;
      O = N = M = null;
      Jh = false;
      Kh = 0;
      nk.current = null;
      if (null === c || null === c.return) {
        T = 1;
        pk = b;
        Y = null;
        break;
      }
      a: {
        var f2 = a, g = c.return, h = c, k2 = b;
        b = Z;
        h.flags |= 32768;
        if (null !== k2 && "object" === typeof k2 && "function" === typeof k2.then) {
          var l2 = k2, m2 = h, q2 = m2.tag;
          if (0 === (m2.mode & 1) && (0 === q2 || 11 === q2 || 15 === q2)) {
            var r2 = m2.alternate;
            r2 ? (m2.updateQueue = r2.updateQueue, m2.memoizedState = r2.memoizedState, m2.lanes = r2.lanes) : (m2.updateQueue = null, m2.memoizedState = null);
          }
          var y2 = Ui(g);
          if (null !== y2) {
            y2.flags &= -257;
            Vi(y2, g, h, f2, b);
            y2.mode & 1 && Si(f2, l2, b);
            b = y2;
            k2 = l2;
            var n2 = b.updateQueue;
            if (null === n2) {
              var t2 = /* @__PURE__ */ new Set();
              t2.add(k2);
              b.updateQueue = t2;
            } else n2.add(k2);
            break a;
          } else {
            if (0 === (b & 1)) {
              Si(f2, l2, b);
              tj();
              break a;
            }
            k2 = Error(p(426));
          }
        } else if (I && h.mode & 1) {
          var J2 = Ui(g);
          if (null !== J2) {
            0 === (J2.flags & 65536) && (J2.flags |= 256);
            Vi(J2, g, h, f2, b);
            Jg(Ji(k2, h));
            break a;
          }
        }
        f2 = k2 = Ji(k2, h);
        4 !== T && (T = 2);
        null === sk ? sk = [f2] : sk.push(f2);
        f2 = g;
        do {
          switch (f2.tag) {
            case 3:
              f2.flags |= 65536;
              b &= -b;
              f2.lanes |= b;
              var x2 = Ni(f2, k2, b);
              ph(f2, x2);
              break a;
            case 1:
              h = k2;
              var w2 = f2.type, u2 = f2.stateNode;
              if (0 === (f2.flags & 128) && ("function" === typeof w2.getDerivedStateFromError || null !== u2 && "function" === typeof u2.componentDidCatch && (null === Ri || !Ri.has(u2)))) {
                f2.flags |= 65536;
                b &= -b;
                f2.lanes |= b;
                var F2 = Qi(f2, h, b);
                ph(f2, F2);
                break a;
              }
          }
          f2 = f2.return;
        } while (null !== f2);
      }
      Sk(c);
    } catch (na) {
      b = na;
      Y === c && null !== c && (Y = c = c.return);
      continue;
    }
    break;
  } while (1);
}
function Jk() {
  var a = mk.current;
  mk.current = Rh;
  return null === a ? Rh : a;
}
function tj() {
  if (0 === T || 3 === T || 2 === T) T = 4;
  null === Q || 0 === (rh & 268435455) && 0 === (qk & 268435455) || Ck(Q, Z);
}
function Ik(a, b) {
  var c = K;
  K |= 2;
  var d = Jk();
  if (Q !== a || Z !== b) uk = null, Kk(a, b);
  do
    try {
      Tk();
      break;
    } catch (e) {
      Mk(a, e);
    }
  while (1);
  $g();
  K = c;
  mk.current = d;
  if (null !== Y) throw Error(p(261));
  Q = null;
  Z = 0;
  return T;
}
function Tk() {
  for (; null !== Y; ) Uk(Y);
}
function Lk() {
  for (; null !== Y && !cc(); ) Uk(Y);
}
function Uk(a) {
  var b = Vk(a.alternate, a, fj);
  a.memoizedProps = a.pendingProps;
  null === b ? Sk(a) : Y = b;
  nk.current = null;
}
function Sk(a) {
  var b = a;
  do {
    var c = b.alternate;
    a = b.return;
    if (0 === (b.flags & 32768)) {
      if (c = Ej(c, b, fj), null !== c) {
        Y = c;
        return;
      }
    } else {
      c = Ij(c, b);
      if (null !== c) {
        c.flags &= 32767;
        Y = c;
        return;
      }
      if (null !== a) a.flags |= 32768, a.subtreeFlags = 0, a.deletions = null;
      else {
        T = 6;
        Y = null;
        return;
      }
    }
    b = b.sibling;
    if (null !== b) {
      Y = b;
      return;
    }
    Y = b = a;
  } while (null !== b);
  0 === T && (T = 5);
}
function Pk(a, b, c) {
  var d = C, e = ok.transition;
  try {
    ok.transition = null, C = 1, Wk(a, b, c, d);
  } finally {
    ok.transition = e, C = d;
  }
  return null;
}
function Wk(a, b, c, d) {
  do
    Hk();
  while (null !== wk);
  if (0 !== (K & 6)) throw Error(p(327));
  c = a.finishedWork;
  var e = a.finishedLanes;
  if (null === c) return null;
  a.finishedWork = null;
  a.finishedLanes = 0;
  if (c === a.current) throw Error(p(177));
  a.callbackNode = null;
  a.callbackPriority = 0;
  var f2 = c.lanes | c.childLanes;
  Bc(a, f2);
  a === Q && (Y = Q = null, Z = 0);
  0 === (c.subtreeFlags & 2064) && 0 === (c.flags & 2064) || vk || (vk = true, Fk(hc, function() {
    Hk();
    return null;
  }));
  f2 = 0 !== (c.flags & 15990);
  if (0 !== (c.subtreeFlags & 15990) || f2) {
    f2 = ok.transition;
    ok.transition = null;
    var g = C;
    C = 1;
    var h = K;
    K |= 4;
    nk.current = null;
    Oj(a, c);
    dk(c, a);
    Oe(Df);
    dd = !!Cf;
    Df = Cf = null;
    a.current = c;
    hk(c);
    dc();
    K = h;
    C = g;
    ok.transition = f2;
  } else a.current = c;
  vk && (vk = false, wk = a, xk = e);
  f2 = a.pendingLanes;
  0 === f2 && (Ri = null);
  mc(c.stateNode);
  Dk(a, B());
  if (null !== b) for (d = a.onRecoverableError, c = 0; c < b.length; c++) e = b[c], d(e.value, { componentStack: e.stack, digest: e.digest });
  if (Oi) throw Oi = false, a = Pi, Pi = null, a;
  0 !== (xk & 1) && 0 !== a.tag && Hk();
  f2 = a.pendingLanes;
  0 !== (f2 & 1) ? a === zk ? yk++ : (yk = 0, zk = a) : yk = 0;
  jg();
  return null;
}
function Hk() {
  if (null !== wk) {
    var a = Dc(xk), b = ok.transition, c = C;
    try {
      ok.transition = null;
      C = 16 > a ? 16 : a;
      if (null === wk) var d = false;
      else {
        a = wk;
        wk = null;
        xk = 0;
        if (0 !== (K & 6)) throw Error(p(331));
        var e = K;
        K |= 4;
        for (V = a.current; null !== V; ) {
          var f2 = V, g = f2.child;
          if (0 !== (V.flags & 16)) {
            var h = f2.deletions;
            if (null !== h) {
              for (var k2 = 0; k2 < h.length; k2++) {
                var l2 = h[k2];
                for (V = l2; null !== V; ) {
                  var m2 = V;
                  switch (m2.tag) {
                    case 0:
                    case 11:
                    case 15:
                      Pj(8, m2, f2);
                  }
                  var q2 = m2.child;
                  if (null !== q2) q2.return = m2, V = q2;
                  else for (; null !== V; ) {
                    m2 = V;
                    var r2 = m2.sibling, y2 = m2.return;
                    Sj(m2);
                    if (m2 === l2) {
                      V = null;
                      break;
                    }
                    if (null !== r2) {
                      r2.return = y2;
                      V = r2;
                      break;
                    }
                    V = y2;
                  }
                }
              }
              var n2 = f2.alternate;
              if (null !== n2) {
                var t2 = n2.child;
                if (null !== t2) {
                  n2.child = null;
                  do {
                    var J2 = t2.sibling;
                    t2.sibling = null;
                    t2 = J2;
                  } while (null !== t2);
                }
              }
              V = f2;
            }
          }
          if (0 !== (f2.subtreeFlags & 2064) && null !== g) g.return = f2, V = g;
          else b: for (; null !== V; ) {
            f2 = V;
            if (0 !== (f2.flags & 2048)) switch (f2.tag) {
              case 0:
              case 11:
              case 15:
                Pj(9, f2, f2.return);
            }
            var x2 = f2.sibling;
            if (null !== x2) {
              x2.return = f2.return;
              V = x2;
              break b;
            }
            V = f2.return;
          }
        }
        var w2 = a.current;
        for (V = w2; null !== V; ) {
          g = V;
          var u2 = g.child;
          if (0 !== (g.subtreeFlags & 2064) && null !== u2) u2.return = g, V = u2;
          else b: for (g = w2; null !== V; ) {
            h = V;
            if (0 !== (h.flags & 2048)) try {
              switch (h.tag) {
                case 0:
                case 11:
                case 15:
                  Qj(9, h);
              }
            } catch (na) {
              W(h, h.return, na);
            }
            if (h === g) {
              V = null;
              break b;
            }
            var F2 = h.sibling;
            if (null !== F2) {
              F2.return = h.return;
              V = F2;
              break b;
            }
            V = h.return;
          }
        }
        K = e;
        jg();
        if (lc && "function" === typeof lc.onPostCommitFiberRoot) try {
          lc.onPostCommitFiberRoot(kc, a);
        } catch (na) {
        }
        d = true;
      }
      return d;
    } finally {
      C = c, ok.transition = b;
    }
  }
  return false;
}
function Xk(a, b, c) {
  b = Ji(c, b);
  b = Ni(a, b, 1);
  a = nh(a, b, 1);
  b = R();
  null !== a && (Ac(a, 1, b), Dk(a, b));
}
function W(a, b, c) {
  if (3 === a.tag) Xk(a, a, c);
  else for (; null !== b; ) {
    if (3 === b.tag) {
      Xk(b, a, c);
      break;
    } else if (1 === b.tag) {
      var d = b.stateNode;
      if ("function" === typeof b.type.getDerivedStateFromError || "function" === typeof d.componentDidCatch && (null === Ri || !Ri.has(d))) {
        a = Ji(c, a);
        a = Qi(b, a, 1);
        b = nh(b, a, 1);
        a = R();
        null !== b && (Ac(b, 1, a), Dk(b, a));
        break;
      }
    }
    b = b.return;
  }
}
function Ti(a, b, c) {
  var d = a.pingCache;
  null !== d && d.delete(b);
  b = R();
  a.pingedLanes |= a.suspendedLanes & c;
  Q === a && (Z & c) === c && (4 === T || 3 === T && (Z & 130023424) === Z && 500 > B() - fk ? Kk(a, 0) : rk |= c);
  Dk(a, b);
}
function Yk(a, b) {
  0 === b && (0 === (a.mode & 1) ? b = 1 : (b = sc, sc <<= 1, 0 === (sc & 130023424) && (sc = 4194304)));
  var c = R();
  a = ih(a, b);
  null !== a && (Ac(a, b, c), Dk(a, c));
}
function uj(a) {
  var b = a.memoizedState, c = 0;
  null !== b && (c = b.retryLane);
  Yk(a, c);
}
function bk(a, b) {
  var c = 0;
  switch (a.tag) {
    case 13:
      var d = a.stateNode;
      var e = a.memoizedState;
      null !== e && (c = e.retryLane);
      break;
    case 19:
      d = a.stateNode;
      break;
    default:
      throw Error(p(314));
  }
  null !== d && d.delete(b);
  Yk(a, c);
}
var Vk;
Vk = function(a, b, c) {
  if (null !== a) if (a.memoizedProps !== b.pendingProps || Wf.current) dh = true;
  else {
    if (0 === (a.lanes & c) && 0 === (b.flags & 128)) return dh = false, yj(a, b, c);
    dh = 0 !== (a.flags & 131072) ? true : false;
  }
  else dh = false, I && 0 !== (b.flags & 1048576) && ug(b, ng, b.index);
  b.lanes = 0;
  switch (b.tag) {
    case 2:
      var d = b.type;
      ij(a, b);
      a = b.pendingProps;
      var e = Yf(b, H.current);
      ch(b, c);
      e = Nh(null, b, d, a, e, c);
      var f2 = Sh();
      b.flags |= 1;
      "object" === typeof e && null !== e && "function" === typeof e.render && void 0 === e.$$typeof ? (b.tag = 1, b.memoizedState = null, b.updateQueue = null, Zf(d) ? (f2 = true, cg(b)) : f2 = false, b.memoizedState = null !== e.state && void 0 !== e.state ? e.state : null, kh(b), e.updater = Ei, b.stateNode = e, e._reactInternals = b, Ii(b, d, a, c), b = jj(null, b, d, true, f2, c)) : (b.tag = 0, I && f2 && vg(b), Xi(null, b, e, c), b = b.child);
      return b;
    case 16:
      d = b.elementType;
      a: {
        ij(a, b);
        a = b.pendingProps;
        e = d._init;
        d = e(d._payload);
        b.type = d;
        e = b.tag = Zk(d);
        a = Ci(d, a);
        switch (e) {
          case 0:
            b = cj(null, b, d, a, c);
            break a;
          case 1:
            b = hj(null, b, d, a, c);
            break a;
          case 11:
            b = Yi(null, b, d, a, c);
            break a;
          case 14:
            b = $i(null, b, d, Ci(d.type, a), c);
            break a;
        }
        throw Error(p(
          306,
          d,
          ""
        ));
      }
      return b;
    case 0:
      return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), cj(a, b, d, e, c);
    case 1:
      return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), hj(a, b, d, e, c);
    case 3:
      a: {
        kj(b);
        if (null === a) throw Error(p(387));
        d = b.pendingProps;
        f2 = b.memoizedState;
        e = f2.element;
        lh(a, b);
        qh(b, d, null, c);
        var g = b.memoizedState;
        d = g.element;
        if (f2.isDehydrated) if (f2 = { element: d, isDehydrated: false, cache: g.cache, pendingSuspenseBoundaries: g.pendingSuspenseBoundaries, transitions: g.transitions }, b.updateQueue.baseState = f2, b.memoizedState = f2, b.flags & 256) {
          e = Ji(Error(p(423)), b);
          b = lj(a, b, d, c, e);
          break a;
        } else if (d !== e) {
          e = Ji(Error(p(424)), b);
          b = lj(a, b, d, c, e);
          break a;
        } else for (yg = Lf(b.stateNode.containerInfo.firstChild), xg = b, I = true, zg = null, c = Vg(b, null, d, c), b.child = c; c; ) c.flags = c.flags & -3 | 4096, c = c.sibling;
        else {
          Ig();
          if (d === e) {
            b = Zi(a, b, c);
            break a;
          }
          Xi(a, b, d, c);
        }
        b = b.child;
      }
      return b;
    case 5:
      return Ah(b), null === a && Eg(b), d = b.type, e = b.pendingProps, f2 = null !== a ? a.memoizedProps : null, g = e.children, Ef(d, e) ? g = null : null !== f2 && Ef(d, f2) && (b.flags |= 32), gj(a, b), Xi(a, b, g, c), b.child;
    case 6:
      return null === a && Eg(b), null;
    case 13:
      return oj(a, b, c);
    case 4:
      return yh(b, b.stateNode.containerInfo), d = b.pendingProps, null === a ? b.child = Ug(b, null, d, c) : Xi(a, b, d, c), b.child;
    case 11:
      return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), Yi(a, b, d, e, c);
    case 7:
      return Xi(a, b, b.pendingProps, c), b.child;
    case 8:
      return Xi(a, b, b.pendingProps.children, c), b.child;
    case 12:
      return Xi(a, b, b.pendingProps.children, c), b.child;
    case 10:
      a: {
        d = b.type._context;
        e = b.pendingProps;
        f2 = b.memoizedProps;
        g = e.value;
        G(Wg, d._currentValue);
        d._currentValue = g;
        if (null !== f2) if (He(f2.value, g)) {
          if (f2.children === e.children && !Wf.current) {
            b = Zi(a, b, c);
            break a;
          }
        } else for (f2 = b.child, null !== f2 && (f2.return = b); null !== f2; ) {
          var h = f2.dependencies;
          if (null !== h) {
            g = f2.child;
            for (var k2 = h.firstContext; null !== k2; ) {
              if (k2.context === d) {
                if (1 === f2.tag) {
                  k2 = mh(-1, c & -c);
                  k2.tag = 2;
                  var l2 = f2.updateQueue;
                  if (null !== l2) {
                    l2 = l2.shared;
                    var m2 = l2.pending;
                    null === m2 ? k2.next = k2 : (k2.next = m2.next, m2.next = k2);
                    l2.pending = k2;
                  }
                }
                f2.lanes |= c;
                k2 = f2.alternate;
                null !== k2 && (k2.lanes |= c);
                bh(
                  f2.return,
                  c,
                  b
                );
                h.lanes |= c;
                break;
              }
              k2 = k2.next;
            }
          } else if (10 === f2.tag) g = f2.type === b.type ? null : f2.child;
          else if (18 === f2.tag) {
            g = f2.return;
            if (null === g) throw Error(p(341));
            g.lanes |= c;
            h = g.alternate;
            null !== h && (h.lanes |= c);
            bh(g, c, b);
            g = f2.sibling;
          } else g = f2.child;
          if (null !== g) g.return = f2;
          else for (g = f2; null !== g; ) {
            if (g === b) {
              g = null;
              break;
            }
            f2 = g.sibling;
            if (null !== f2) {
              f2.return = g.return;
              g = f2;
              break;
            }
            g = g.return;
          }
          f2 = g;
        }
        Xi(a, b, e.children, c);
        b = b.child;
      }
      return b;
    case 9:
      return e = b.type, d = b.pendingProps.children, ch(b, c), e = eh(e), d = d(e), b.flags |= 1, Xi(a, b, d, c), b.child;
    case 14:
      return d = b.type, e = Ci(d, b.pendingProps), e = Ci(d.type, e), $i(a, b, d, e, c);
    case 15:
      return bj(a, b, b.type, b.pendingProps, c);
    case 17:
      return d = b.type, e = b.pendingProps, e = b.elementType === d ? e : Ci(d, e), ij(a, b), b.tag = 1, Zf(d) ? (a = true, cg(b)) : a = false, ch(b, c), Gi(b, d, e), Ii(b, d, e, c), jj(null, b, d, true, a, c);
    case 19:
      return xj(a, b, c);
    case 22:
      return dj(a, b, c);
  }
  throw Error(p(156, b.tag));
};
function Fk(a, b) {
  return ac(a, b);
}
function $k(a, b, c, d) {
  this.tag = a;
  this.key = c;
  this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null;
  this.index = 0;
  this.ref = null;
  this.pendingProps = b;
  this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null;
  this.mode = d;
  this.subtreeFlags = this.flags = 0;
  this.deletions = null;
  this.childLanes = this.lanes = 0;
  this.alternate = null;
}
function Bg(a, b, c, d) {
  return new $k(a, b, c, d);
}
function aj(a) {
  a = a.prototype;
  return !(!a || !a.isReactComponent);
}
function Zk(a) {
  if ("function" === typeof a) return aj(a) ? 1 : 0;
  if (void 0 !== a && null !== a) {
    a = a.$$typeof;
    if (a === Da) return 11;
    if (a === Ga) return 14;
  }
  return 2;
}
function Pg(a, b) {
  var c = a.alternate;
  null === c ? (c = Bg(a.tag, b, a.key, a.mode), c.elementType = a.elementType, c.type = a.type, c.stateNode = a.stateNode, c.alternate = a, a.alternate = c) : (c.pendingProps = b, c.type = a.type, c.flags = 0, c.subtreeFlags = 0, c.deletions = null);
  c.flags = a.flags & 14680064;
  c.childLanes = a.childLanes;
  c.lanes = a.lanes;
  c.child = a.child;
  c.memoizedProps = a.memoizedProps;
  c.memoizedState = a.memoizedState;
  c.updateQueue = a.updateQueue;
  b = a.dependencies;
  c.dependencies = null === b ? null : { lanes: b.lanes, firstContext: b.firstContext };
  c.sibling = a.sibling;
  c.index = a.index;
  c.ref = a.ref;
  return c;
}
function Rg(a, b, c, d, e, f2) {
  var g = 2;
  d = a;
  if ("function" === typeof a) aj(a) && (g = 1);
  else if ("string" === typeof a) g = 5;
  else a: switch (a) {
    case ya:
      return Tg(c.children, e, f2, b);
    case za:
      g = 8;
      e |= 8;
      break;
    case Aa:
      return a = Bg(12, c, b, e | 2), a.elementType = Aa, a.lanes = f2, a;
    case Ea:
      return a = Bg(13, c, b, e), a.elementType = Ea, a.lanes = f2, a;
    case Fa:
      return a = Bg(19, c, b, e), a.elementType = Fa, a.lanes = f2, a;
    case Ia:
      return pj(c, e, f2, b);
    default:
      if ("object" === typeof a && null !== a) switch (a.$$typeof) {
        case Ba:
          g = 10;
          break a;
        case Ca:
          g = 9;
          break a;
        case Da:
          g = 11;
          break a;
        case Ga:
          g = 14;
          break a;
        case Ha:
          g = 16;
          d = null;
          break a;
      }
      throw Error(p(130, null == a ? a : typeof a, ""));
  }
  b = Bg(g, c, b, e);
  b.elementType = a;
  b.type = d;
  b.lanes = f2;
  return b;
}
function Tg(a, b, c, d) {
  a = Bg(7, a, d, b);
  a.lanes = c;
  return a;
}
function pj(a, b, c, d) {
  a = Bg(22, a, d, b);
  a.elementType = Ia;
  a.lanes = c;
  a.stateNode = { isHidden: false };
  return a;
}
function Qg(a, b, c) {
  a = Bg(6, a, null, b);
  a.lanes = c;
  return a;
}
function Sg(a, b, c) {
  b = Bg(4, null !== a.children ? a.children : [], a.key, b);
  b.lanes = c;
  b.stateNode = { containerInfo: a.containerInfo, pendingChildren: null, implementation: a.implementation };
  return b;
}
function al(a, b, c, d, e) {
  this.tag = b;
  this.containerInfo = a;
  this.finishedWork = this.pingCache = this.current = this.pendingChildren = null;
  this.timeoutHandle = -1;
  this.callbackNode = this.pendingContext = this.context = null;
  this.callbackPriority = 0;
  this.eventTimes = zc(0);
  this.expirationTimes = zc(-1);
  this.entangledLanes = this.finishedLanes = this.mutableReadLanes = this.expiredLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0;
  this.entanglements = zc(0);
  this.identifierPrefix = d;
  this.onRecoverableError = e;
  this.mutableSourceEagerHydrationData = null;
}
function bl(a, b, c, d, e, f2, g, h, k2) {
  a = new al(a, b, c, h, k2);
  1 === b ? (b = 1, true === f2 && (b |= 8)) : b = 0;
  f2 = Bg(3, null, null, b);
  a.current = f2;
  f2.stateNode = a;
  f2.memoizedState = { element: d, isDehydrated: c, cache: null, transitions: null, pendingSuspenseBoundaries: null };
  kh(f2);
  return a;
}
function cl(a, b, c) {
  var d = 3 < arguments.length && void 0 !== arguments[3] ? arguments[3] : null;
  return { $$typeof: wa, key: null == d ? null : "" + d, children: a, containerInfo: b, implementation: c };
}
function dl(a) {
  if (!a) return Vf;
  a = a._reactInternals;
  a: {
    if (Vb(a) !== a || 1 !== a.tag) throw Error(p(170));
    var b = a;
    do {
      switch (b.tag) {
        case 3:
          b = b.stateNode.context;
          break a;
        case 1:
          if (Zf(b.type)) {
            b = b.stateNode.__reactInternalMemoizedMergedChildContext;
            break a;
          }
      }
      b = b.return;
    } while (null !== b);
    throw Error(p(171));
  }
  if (1 === a.tag) {
    var c = a.type;
    if (Zf(c)) return bg(a, c, b);
  }
  return b;
}
function el(a, b, c, d, e, f2, g, h, k2) {
  a = bl(c, d, true, a, e, f2, g, h, k2);
  a.context = dl(null);
  c = a.current;
  d = R();
  e = yi(c);
  f2 = mh(d, e);
  f2.callback = void 0 !== b && null !== b ? b : null;
  nh(c, f2, e);
  a.current.lanes = e;
  Ac(a, e, d);
  Dk(a, d);
  return a;
}
function fl(a, b, c, d) {
  var e = b.current, f2 = R(), g = yi(e);
  c = dl(c);
  null === b.context ? b.context = c : b.pendingContext = c;
  b = mh(f2, g);
  b.payload = { element: a };
  d = void 0 === d ? null : d;
  null !== d && (b.callback = d);
  a = nh(e, b, g);
  null !== a && (gi(a, e, g, f2), oh(a, e, g));
  return g;
}
function gl(a) {
  a = a.current;
  if (!a.child) return null;
  switch (a.child.tag) {
    case 5:
      return a.child.stateNode;
    default:
      return a.child.stateNode;
  }
}
function hl(a, b) {
  a = a.memoizedState;
  if (null !== a && null !== a.dehydrated) {
    var c = a.retryLane;
    a.retryLane = 0 !== c && c < b ? c : b;
  }
}
function il(a, b) {
  hl(a, b);
  (a = a.alternate) && hl(a, b);
}
function jl() {
  return null;
}
var kl = "function" === typeof reportError ? reportError : function(a) {
  console.error(a);
};
function ll(a) {
  this._internalRoot = a;
}
ml.prototype.render = ll.prototype.render = function(a) {
  var b = this._internalRoot;
  if (null === b) throw Error(p(409));
  fl(a, b, null, null);
};
ml.prototype.unmount = ll.prototype.unmount = function() {
  var a = this._internalRoot;
  if (null !== a) {
    this._internalRoot = null;
    var b = a.containerInfo;
    Rk(function() {
      fl(null, a, null, null);
    });
    b[uf] = null;
  }
};
function ml(a) {
  this._internalRoot = a;
}
ml.prototype.unstable_scheduleHydration = function(a) {
  if (a) {
    var b = Hc();
    a = { blockedOn: null, target: a, priority: b };
    for (var c = 0; c < Qc.length && 0 !== b && b < Qc[c].priority; c++) ;
    Qc.splice(c, 0, a);
    0 === c && Vc(a);
  }
};
function nl(a) {
  return !(!a || 1 !== a.nodeType && 9 !== a.nodeType && 11 !== a.nodeType);
}
function ol(a) {
  return !(!a || 1 !== a.nodeType && 9 !== a.nodeType && 11 !== a.nodeType && (8 !== a.nodeType || " react-mount-point-unstable " !== a.nodeValue));
}
function pl() {
}
function ql(a, b, c, d, e) {
  if (e) {
    if ("function" === typeof d) {
      var f2 = d;
      d = function() {
        var a2 = gl(g);
        f2.call(a2);
      };
    }
    var g = el(b, d, a, 0, null, false, false, "", pl);
    a._reactRootContainer = g;
    a[uf] = g.current;
    sf(8 === a.nodeType ? a.parentNode : a);
    Rk();
    return g;
  }
  for (; e = a.lastChild; ) a.removeChild(e);
  if ("function" === typeof d) {
    var h = d;
    d = function() {
      var a2 = gl(k2);
      h.call(a2);
    };
  }
  var k2 = bl(a, 0, false, null, null, false, false, "", pl);
  a._reactRootContainer = k2;
  a[uf] = k2.current;
  sf(8 === a.nodeType ? a.parentNode : a);
  Rk(function() {
    fl(b, k2, c, d);
  });
  return k2;
}
function rl(a, b, c, d, e) {
  var f2 = c._reactRootContainer;
  if (f2) {
    var g = f2;
    if ("function" === typeof e) {
      var h = e;
      e = function() {
        var a2 = gl(g);
        h.call(a2);
      };
    }
    fl(b, g, a, e);
  } else g = ql(c, b, a, e, d);
  return gl(g);
}
Ec = function(a) {
  switch (a.tag) {
    case 3:
      var b = a.stateNode;
      if (b.current.memoizedState.isDehydrated) {
        var c = tc(b.pendingLanes);
        0 !== c && (Cc(b, c | 1), Dk(b, B()), 0 === (K & 6) && (Gj = B() + 500, jg()));
      }
      break;
    case 13:
      Rk(function() {
        var b2 = ih(a, 1);
        if (null !== b2) {
          var c2 = R();
          gi(b2, a, 1, c2);
        }
      }), il(a, 1);
  }
};
Fc = function(a) {
  if (13 === a.tag) {
    var b = ih(a, 134217728);
    if (null !== b) {
      var c = R();
      gi(b, a, 134217728, c);
    }
    il(a, 134217728);
  }
};
Gc = function(a) {
  if (13 === a.tag) {
    var b = yi(a), c = ih(a, b);
    if (null !== c) {
      var d = R();
      gi(c, a, b, d);
    }
    il(a, b);
  }
};
Hc = function() {
  return C;
};
Ic = function(a, b) {
  var c = C;
  try {
    return C = a, b();
  } finally {
    C = c;
  }
};
yb = function(a, b, c) {
  switch (b) {
    case "input":
      bb(a, c);
      b = c.name;
      if ("radio" === c.type && null != b) {
        for (c = a; c.parentNode; ) c = c.parentNode;
        c = c.querySelectorAll("input[name=" + JSON.stringify("" + b) + '][type="radio"]');
        for (b = 0; b < c.length; b++) {
          var d = c[b];
          if (d !== a && d.form === a.form) {
            var e = Db(d);
            if (!e) throw Error(p(90));
            Wa(d);
            bb(d, e);
          }
        }
      }
      break;
    case "textarea":
      ib(a, c);
      break;
    case "select":
      b = c.value, null != b && fb(a, !!c.multiple, b, false);
  }
};
Gb = Qk;
Hb = Rk;
var sl = { usingClientEntryPoint: false, Events: [Cb, ue, Db, Eb, Fb, Qk] }, tl = { findFiberByHostInstance: Wc, bundleType: 0, version: "18.3.1", rendererPackageName: "react-dom" };
var ul = { bundleType: tl.bundleType, version: tl.version, rendererPackageName: tl.rendererPackageName, rendererConfig: tl.rendererConfig, overrideHookState: null, overrideHookStateDeletePath: null, overrideHookStateRenamePath: null, overrideProps: null, overridePropsDeletePath: null, overridePropsRenamePath: null, setErrorHandler: null, setSuspenseHandler: null, scheduleUpdate: null, currentDispatcherRef: ua.ReactCurrentDispatcher, findHostInstanceByFiber: function(a) {
  a = Zb(a);
  return null === a ? null : a.stateNode;
}, findFiberByHostInstance: tl.findFiberByHostInstance || jl, findHostInstancesForRefresh: null, scheduleRefresh: null, scheduleRoot: null, setRefreshHandler: null, getCurrentFiber: null, reconcilerVersion: "18.3.1-next-f1338f8080-20240426" };
if ("undefined" !== typeof __REACT_DEVTOOLS_GLOBAL_HOOK__) {
  var vl = __REACT_DEVTOOLS_GLOBAL_HOOK__;
  if (!vl.isDisabled && vl.supportsFiber) try {
    kc = vl.inject(ul), lc = vl;
  } catch (a) {
  }
}
reactDom_production_min.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = sl;
reactDom_production_min.createPortal = function(a, b) {
  var c = 2 < arguments.length && void 0 !== arguments[2] ? arguments[2] : null;
  if (!nl(b)) throw Error(p(200));
  return cl(a, b, null, c);
};
reactDom_production_min.createRoot = function(a, b) {
  if (!nl(a)) throw Error(p(299));
  var c = false, d = "", e = kl;
  null !== b && void 0 !== b && (true === b.unstable_strictMode && (c = true), void 0 !== b.identifierPrefix && (d = b.identifierPrefix), void 0 !== b.onRecoverableError && (e = b.onRecoverableError));
  b = bl(a, 1, false, null, null, c, false, d, e);
  a[uf] = b.current;
  sf(8 === a.nodeType ? a.parentNode : a);
  return new ll(b);
};
reactDom_production_min.findDOMNode = function(a) {
  if (null == a) return null;
  if (1 === a.nodeType) return a;
  var b = a._reactInternals;
  if (void 0 === b) {
    if ("function" === typeof a.render) throw Error(p(188));
    a = Object.keys(a).join(",");
    throw Error(p(268, a));
  }
  a = Zb(b);
  a = null === a ? null : a.stateNode;
  return a;
};
reactDom_production_min.flushSync = function(a) {
  return Rk(a);
};
reactDom_production_min.hydrate = function(a, b, c) {
  if (!ol(b)) throw Error(p(200));
  return rl(null, a, b, true, c);
};
reactDom_production_min.hydrateRoot = function(a, b, c) {
  if (!nl(a)) throw Error(p(405));
  var d = null != c && c.hydratedSources || null, e = false, f2 = "", g = kl;
  null !== c && void 0 !== c && (true === c.unstable_strictMode && (e = true), void 0 !== c.identifierPrefix && (f2 = c.identifierPrefix), void 0 !== c.onRecoverableError && (g = c.onRecoverableError));
  b = el(b, null, a, 1, null != c ? c : null, e, false, f2, g);
  a[uf] = b.current;
  sf(a);
  if (d) for (a = 0; a < d.length; a++) c = d[a], e = c._getVersion, e = e(c._source), null == b.mutableSourceEagerHydrationData ? b.mutableSourceEagerHydrationData = [c, e] : b.mutableSourceEagerHydrationData.push(
    c,
    e
  );
  return new ml(b);
};
reactDom_production_min.render = function(a, b, c) {
  if (!ol(b)) throw Error(p(200));
  return rl(null, a, b, false, c);
};
reactDom_production_min.unmountComponentAtNode = function(a) {
  if (!ol(a)) throw Error(p(40));
  return a._reactRootContainer ? (Rk(function() {
    rl(null, null, a, false, function() {
      a._reactRootContainer = null;
      a[uf] = null;
    });
  }), true) : false;
};
reactDom_production_min.unstable_batchedUpdates = Qk;
reactDom_production_min.unstable_renderSubtreeIntoContainer = function(a, b, c, d) {
  if (!ol(c)) throw Error(p(200));
  if (null == a || void 0 === a._reactInternals) throw Error(p(38));
  return rl(a, b, c, false, d);
};
reactDom_production_min.version = "18.3.1-next-f1338f8080-20240426";
function checkDCE() {
  if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ === "undefined" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE !== "function") {
    return;
  }
  try {
    __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(checkDCE);
  } catch (err) {
    console.error(err);
  }
}
{
  checkDCE();
  reactDom.exports = reactDom_production_min;
}
var reactDomExports = reactDom.exports;
var m = reactDomExports;
{
  client.createRoot = m.createRoot;
  client.hydrateRoot = m.hydrateRoot;
}
const scriptRel = function detectScriptRel() {
  const relList = typeof document !== "undefined" && document.createElement("link").relList;
  return relList && relList.supports && relList.supports("modulepreload") ? "modulepreload" : "preload";
}();
const assetsURL = function(dep, importerUrl) {
  return new URL(dep, importerUrl).href;
};
const seen = {};
const __vitePreload = function preload(baseModule, deps, importerUrl) {
  let promise = Promise.resolve();
  if (deps && deps.length > 0) {
    const links = document.getElementsByTagName("link");
    const cspNonceMeta = document.querySelector(
      "meta[property=csp-nonce]"
    );
    const cspNonce = cspNonceMeta?.nonce || cspNonceMeta?.getAttribute("nonce");
    promise = Promise.allSettled(
      deps.map((dep) => {
        dep = assetsURL(dep, importerUrl);
        if (dep in seen) return;
        seen[dep] = true;
        const isCss = dep.endsWith(".css");
        const cssSelector = isCss ? '[rel="stylesheet"]' : "";
        const isBaseRelative = !!importerUrl;
        if (isBaseRelative) {
          for (let i = links.length - 1; i >= 0; i--) {
            const link2 = links[i];
            if (link2.href === dep && (!isCss || link2.rel === "stylesheet")) {
              return;
            }
          }
        } else if (document.querySelector(`link[href="${dep}"]${cssSelector}`)) {
          return;
        }
        const link = document.createElement("link");
        link.rel = isCss ? "stylesheet" : scriptRel;
        if (!isCss) {
          link.as = "script";
        }
        link.crossOrigin = "";
        link.href = dep;
        if (cspNonce) {
          link.setAttribute("nonce", cspNonce);
        }
        document.head.appendChild(link);
        if (isCss) {
          return new Promise((res, rej) => {
            link.addEventListener("load", res);
            link.addEventListener(
              "error",
              () => rej(new Error(`Unable to preload CSS for ${dep}`))
            );
          });
        }
      })
    );
  }
  function handlePreloadError(err) {
    const e = new Event("vite:preloadError", {
      cancelable: true
    });
    e.payload = err;
    window.dispatchEvent(e);
    if (!e.defaultPrevented) {
      throw err;
    }
  }
  return promise.then((res) => {
    for (const item of res || []) {
      if (item.status !== "rejected") continue;
      handlePreloadError(item.reason);
    }
    return baseModule().catch(handlePreloadError);
  });
};
const __vite_import_meta_env__$2 = {};
const createStoreImpl = (createState) => {
  let state;
  const listeners = /* @__PURE__ */ new Set();
  const setState = (partial, replace) => {
    const nextState = typeof partial === "function" ? partial(state) : partial;
    if (!Object.is(nextState, state)) {
      const previousState = state;
      state = (replace != null ? replace : typeof nextState !== "object" || nextState === null) ? nextState : Object.assign({}, state, nextState);
      listeners.forEach((listener) => listener(state, previousState));
    }
  };
  const getState = () => state;
  const getInitialState = () => initialState;
  const subscribe = (listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };
  const destroy = () => {
    if ((__vite_import_meta_env__$2 ? "production" : void 0) !== "production") {
      console.warn(
        "[DEPRECATED] The `destroy` method will be unsupported in a future version. Instead use unsubscribe function returned by subscribe. Everything will be garbage-collected if store is garbage-collected."
      );
    }
    listeners.clear();
  };
  const api = { setState, getState, getInitialState, subscribe, destroy };
  const initialState = state = createState(setState, getState, api);
  return api;
};
const createStore = (createState) => createState ? createStoreImpl(createState) : createStoreImpl;
var withSelector = { exports: {} };
var withSelector_production = {};
var shim$2 = { exports: {} };
var useSyncExternalStoreShim_production = {};
/**
 * @license React
 * use-sync-external-store-shim.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */
var React$1 = reactExports;
function is$1(x2, y2) {
  return x2 === y2 && (0 !== x2 || 1 / x2 === 1 / y2) || x2 !== x2 && y2 !== y2;
}
var objectIs$1 = "function" === typeof Object.is ? Object.is : is$1, useState = React$1.useState, useEffect$1 = React$1.useEffect, useLayoutEffect = React$1.useLayoutEffect, useDebugValue$2 = React$1.useDebugValue;
function useSyncExternalStore$2(subscribe, getSnapshot) {
  var value = getSnapshot(), _useState = useState({ inst: { value, getSnapshot } }), inst = _useState[0].inst, forceUpdate = _useState[1];
  useLayoutEffect(
    function() {
      inst.value = value;
      inst.getSnapshot = getSnapshot;
      checkIfSnapshotChanged(inst) && forceUpdate({ inst });
    },
    [subscribe, value, getSnapshot]
  );
  useEffect$1(
    function() {
      checkIfSnapshotChanged(inst) && forceUpdate({ inst });
      return subscribe(function() {
        checkIfSnapshotChanged(inst) && forceUpdate({ inst });
      });
    },
    [subscribe]
  );
  useDebugValue$2(value);
  return value;
}
function checkIfSnapshotChanged(inst) {
  var latestGetSnapshot = inst.getSnapshot;
  inst = inst.value;
  try {
    var nextValue = latestGetSnapshot();
    return !objectIs$1(inst, nextValue);
  } catch (error) {
    return true;
  }
}
function useSyncExternalStore$1(subscribe, getSnapshot) {
  return getSnapshot();
}
var shim$1 = "undefined" === typeof window || "undefined" === typeof window.document || "undefined" === typeof window.document.createElement ? useSyncExternalStore$1 : useSyncExternalStore$2;
useSyncExternalStoreShim_production.useSyncExternalStore = void 0 !== React$1.useSyncExternalStore ? React$1.useSyncExternalStore : shim$1;
{
  shim$2.exports = useSyncExternalStoreShim_production;
}
var shimExports = shim$2.exports;
/**
 * @license React
 * use-sync-external-store-shim/with-selector.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */
var React = reactExports, shim = shimExports;
function is(x2, y2) {
  return x2 === y2 && (0 !== x2 || 1 / x2 === 1 / y2) || x2 !== x2 && y2 !== y2;
}
var objectIs = "function" === typeof Object.is ? Object.is : is, useSyncExternalStore = shim.useSyncExternalStore, useRef = React.useRef, useEffect = React.useEffect, useMemo = React.useMemo, useDebugValue$1 = React.useDebugValue;
withSelector_production.useSyncExternalStoreWithSelector = function(subscribe, getSnapshot, getServerSnapshot, selector, isEqual) {
  var instRef = useRef(null);
  if (null === instRef.current) {
    var inst = { hasValue: false, value: null };
    instRef.current = inst;
  } else inst = instRef.current;
  instRef = useMemo(
    function() {
      function memoizedSelector(nextSnapshot) {
        if (!hasMemo) {
          hasMemo = true;
          memoizedSnapshot = nextSnapshot;
          nextSnapshot = selector(nextSnapshot);
          if (void 0 !== isEqual && inst.hasValue) {
            var currentSelection = inst.value;
            if (isEqual(currentSelection, nextSnapshot))
              return memoizedSelection = currentSelection;
          }
          return memoizedSelection = nextSnapshot;
        }
        currentSelection = memoizedSelection;
        if (objectIs(memoizedSnapshot, nextSnapshot)) return currentSelection;
        var nextSelection = selector(nextSnapshot);
        if (void 0 !== isEqual && isEqual(currentSelection, nextSelection))
          return memoizedSnapshot = nextSnapshot, currentSelection;
        memoizedSnapshot = nextSnapshot;
        return memoizedSelection = nextSelection;
      }
      var hasMemo = false, memoizedSnapshot, memoizedSelection, maybeGetServerSnapshot = void 0 === getServerSnapshot ? null : getServerSnapshot;
      return [
        function() {
          return memoizedSelector(getSnapshot());
        },
        null === maybeGetServerSnapshot ? void 0 : function() {
          return memoizedSelector(maybeGetServerSnapshot());
        }
      ];
    },
    [getSnapshot, getServerSnapshot, selector, isEqual]
  );
  var value = useSyncExternalStore(subscribe, instRef[0], instRef[1]);
  useEffect(
    function() {
      inst.hasValue = true;
      inst.value = value;
    },
    [value]
  );
  useDebugValue$1(value);
  return value;
};
{
  withSelector.exports = withSelector_production;
}
var withSelectorExports = withSelector.exports;
const useSyncExternalStoreExports = /* @__PURE__ */ getDefaultExportFromCjs(withSelectorExports);
const __vite_import_meta_env__$1 = {};
const { useDebugValue } = React$2;
const { useSyncExternalStoreWithSelector } = useSyncExternalStoreExports;
let didWarnAboutEqualityFn = false;
const identity = (arg) => arg;
function useStore(api, selector = identity, equalityFn) {
  if ((__vite_import_meta_env__$1 ? "production" : void 0) !== "production" && equalityFn && !didWarnAboutEqualityFn) {
    console.warn(
      "[DEPRECATED] Use `createWithEqualityFn` instead of `create` or use `useStoreWithEqualityFn` instead of `useStore`. They can be imported from 'zustand/traditional'. https://github.com/pmndrs/zustand/discussions/1937"
    );
    didWarnAboutEqualityFn = true;
  }
  const slice = useSyncExternalStoreWithSelector(
    api.subscribe,
    api.getState,
    api.getServerState || api.getInitialState,
    selector,
    equalityFn
  );
  useDebugValue(slice);
  return slice;
}
const createImpl = (createState) => {
  if ((__vite_import_meta_env__$1 ? "production" : void 0) !== "production" && typeof createState !== "function") {
    console.warn(
      "[DEPRECATED] Passing a vanilla store will be unsupported in a future version. Instead use `import { useStore } from 'zustand'`."
    );
  }
  const api = typeof createState === "function" ? createStore(createState) : createState;
  const useBoundStore = (selector, equalityFn) => useStore(api, selector, equalityFn);
  Object.assign(useBoundStore, api);
  return useBoundStore;
};
const create = (createState) => createState ? createImpl(createState) : createImpl;
const __vite_import_meta_env__ = {};
function createJSONStorage(getStorage, options) {
  let storage;
  try {
    storage = getStorage();
  } catch (_e) {
    return;
  }
  const persistStorage = {
    getItem: (name) => {
      var _a;
      const parse = (str2) => {
        if (str2 === null) {
          return null;
        }
        return JSON.parse(str2, void 0);
      };
      const str = (_a = storage.getItem(name)) != null ? _a : null;
      if (str instanceof Promise) {
        return str.then(parse);
      }
      return parse(str);
    },
    setItem: (name, newValue) => storage.setItem(
      name,
      JSON.stringify(newValue, void 0)
    ),
    removeItem: (name) => storage.removeItem(name)
  };
  return persistStorage;
}
const toThenable = (fn) => (input) => {
  try {
    const result = fn(input);
    if (result instanceof Promise) {
      return result;
    }
    return {
      then(onFulfilled) {
        return toThenable(onFulfilled)(result);
      },
      catch(_onRejected) {
        return this;
      }
    };
  } catch (e) {
    return {
      then(_onFulfilled) {
        return this;
      },
      catch(onRejected) {
        return toThenable(onRejected)(e);
      }
    };
  }
};
const oldImpl = (config, baseOptions) => (set, get, api) => {
  let options = {
    getStorage: () => localStorage,
    serialize: JSON.stringify,
    deserialize: JSON.parse,
    partialize: (state) => state,
    version: 0,
    merge: (persistedState, currentState) => ({
      ...currentState,
      ...persistedState
    }),
    ...baseOptions
  };
  let hasHydrated = false;
  const hydrationListeners = /* @__PURE__ */ new Set();
  const finishHydrationListeners = /* @__PURE__ */ new Set();
  let storage;
  try {
    storage = options.getStorage();
  } catch (_e) {
  }
  if (!storage) {
    return config(
      (...args) => {
        console.warn(
          `[zustand persist middleware] Unable to update item '${options.name}', the given storage is currently unavailable.`
        );
        set(...args);
      },
      get,
      api
    );
  }
  const thenableSerialize = toThenable(options.serialize);
  const setItem = () => {
    const state = options.partialize({ ...get() });
    let errorInSync;
    const thenable = thenableSerialize({ state, version: options.version }).then(
      (serializedValue) => storage.setItem(options.name, serializedValue)
    ).catch((e) => {
      errorInSync = e;
    });
    if (errorInSync) {
      throw errorInSync;
    }
    return thenable;
  };
  const savedSetState = api.setState;
  api.setState = (state, replace) => {
    savedSetState(state, replace);
    void setItem();
  };
  const configResult = config(
    (...args) => {
      set(...args);
      void setItem();
    },
    get,
    api
  );
  let stateFromStorage;
  const hydrate = () => {
    var _a;
    if (!storage) return;
    hasHydrated = false;
    hydrationListeners.forEach((cb2) => cb2(get()));
    const postRehydrationCallback = ((_a = options.onRehydrateStorage) == null ? void 0 : _a.call(options, get())) || void 0;
    return toThenable(storage.getItem.bind(storage))(options.name).then((storageValue) => {
      if (storageValue) {
        return options.deserialize(storageValue);
      }
    }).then((deserializedStorageValue) => {
      if (deserializedStorageValue) {
        if (typeof deserializedStorageValue.version === "number" && deserializedStorageValue.version !== options.version) {
          if (options.migrate) {
            return options.migrate(
              deserializedStorageValue.state,
              deserializedStorageValue.version
            );
          }
          console.error(
            `State loaded from storage couldn't be migrated since no migrate function was provided`
          );
        } else {
          return deserializedStorageValue.state;
        }
      }
    }).then((migratedState) => {
      var _a2;
      stateFromStorage = options.merge(
        migratedState,
        (_a2 = get()) != null ? _a2 : configResult
      );
      set(stateFromStorage, true);
      return setItem();
    }).then(() => {
      postRehydrationCallback == null ? void 0 : postRehydrationCallback(stateFromStorage, void 0);
      hasHydrated = true;
      finishHydrationListeners.forEach((cb2) => cb2(stateFromStorage));
    }).catch((e) => {
      postRehydrationCallback == null ? void 0 : postRehydrationCallback(void 0, e);
    });
  };
  api.persist = {
    setOptions: (newOptions) => {
      options = {
        ...options,
        ...newOptions
      };
      if (newOptions.getStorage) {
        storage = newOptions.getStorage();
      }
    },
    clearStorage: () => {
      storage == null ? void 0 : storage.removeItem(options.name);
    },
    getOptions: () => options,
    rehydrate: () => hydrate(),
    hasHydrated: () => hasHydrated,
    onHydrate: (cb2) => {
      hydrationListeners.add(cb2);
      return () => {
        hydrationListeners.delete(cb2);
      };
    },
    onFinishHydration: (cb2) => {
      finishHydrationListeners.add(cb2);
      return () => {
        finishHydrationListeners.delete(cb2);
      };
    }
  };
  hydrate();
  return stateFromStorage || configResult;
};
const newImpl = (config, baseOptions) => (set, get, api) => {
  let options = {
    storage: createJSONStorage(() => localStorage),
    partialize: (state) => state,
    version: 0,
    merge: (persistedState, currentState) => ({
      ...currentState,
      ...persistedState
    }),
    ...baseOptions
  };
  let hasHydrated = false;
  const hydrationListeners = /* @__PURE__ */ new Set();
  const finishHydrationListeners = /* @__PURE__ */ new Set();
  let storage = options.storage;
  if (!storage) {
    return config(
      (...args) => {
        console.warn(
          `[zustand persist middleware] Unable to update item '${options.name}', the given storage is currently unavailable.`
        );
        set(...args);
      },
      get,
      api
    );
  }
  const setItem = () => {
    const state = options.partialize({ ...get() });
    return storage.setItem(options.name, {
      state,
      version: options.version
    });
  };
  const savedSetState = api.setState;
  api.setState = (state, replace) => {
    savedSetState(state, replace);
    void setItem();
  };
  const configResult = config(
    (...args) => {
      set(...args);
      void setItem();
    },
    get,
    api
  );
  api.getInitialState = () => configResult;
  let stateFromStorage;
  const hydrate = () => {
    var _a, _b;
    if (!storage) return;
    hasHydrated = false;
    hydrationListeners.forEach((cb2) => {
      var _a2;
      return cb2((_a2 = get()) != null ? _a2 : configResult);
    });
    const postRehydrationCallback = ((_b = options.onRehydrateStorage) == null ? void 0 : _b.call(options, (_a = get()) != null ? _a : configResult)) || void 0;
    return toThenable(storage.getItem.bind(storage))(options.name).then((deserializedStorageValue) => {
      if (deserializedStorageValue) {
        if (typeof deserializedStorageValue.version === "number" && deserializedStorageValue.version !== options.version) {
          if (options.migrate) {
            return [
              true,
              options.migrate(
                deserializedStorageValue.state,
                deserializedStorageValue.version
              )
            ];
          }
          console.error(
            `State loaded from storage couldn't be migrated since no migrate function was provided`
          );
        } else {
          return [false, deserializedStorageValue.state];
        }
      }
      return [false, void 0];
    }).then((migrationResult) => {
      var _a2;
      const [migrated, migratedState] = migrationResult;
      stateFromStorage = options.merge(
        migratedState,
        (_a2 = get()) != null ? _a2 : configResult
      );
      set(stateFromStorage, true);
      if (migrated) {
        return setItem();
      }
    }).then(() => {
      postRehydrationCallback == null ? void 0 : postRehydrationCallback(stateFromStorage, void 0);
      stateFromStorage = get();
      hasHydrated = true;
      finishHydrationListeners.forEach((cb2) => cb2(stateFromStorage));
    }).catch((e) => {
      postRehydrationCallback == null ? void 0 : postRehydrationCallback(void 0, e);
    });
  };
  api.persist = {
    setOptions: (newOptions) => {
      options = {
        ...options,
        ...newOptions
      };
      if (newOptions.storage) {
        storage = newOptions.storage;
      }
    },
    clearStorage: () => {
      storage == null ? void 0 : storage.removeItem(options.name);
    },
    getOptions: () => options,
    rehydrate: () => hydrate(),
    hasHydrated: () => hasHydrated,
    onHydrate: (cb2) => {
      hydrationListeners.add(cb2);
      return () => {
        hydrationListeners.delete(cb2);
      };
    },
    onFinishHydration: (cb2) => {
      finishHydrationListeners.add(cb2);
      return () => {
        finishHydrationListeners.delete(cb2);
      };
    }
  };
  if (!options.skipHydration) {
    hydrate();
  }
  return stateFromStorage || configResult;
};
const persistImpl = (config, baseOptions) => {
  if ("getStorage" in baseOptions || "serialize" in baseOptions || "deserialize" in baseOptions) {
    if ((__vite_import_meta_env__ ? "production" : void 0) !== "production") {
      console.warn(
        "[DEPRECATED] `getStorage`, `serialize` and `deserialize` options are deprecated. Use `storage` option instead."
      );
    }
    return oldImpl(config, baseOptions);
  }
  return newImpl(config, baseOptions);
};
const persist = persistImpl;
const useProjectStore = create()(
  persist(
    (set, get) => ({
      projects: [],
      activeProjectId: null,
      previewProjectId: null,
      // Orchestrator state
      orchestratorProjects: [],
      selectedOrchestratorIds: [],
      orchestratorLoading: false,
      orchestratorError: null,
      // RE projects state
      reProjects: [],
      reProjectsLoading: false,
      selectedREProject: null,
      addProject: (projectData) => {
        const id2 = crypto.randomUUID();
        const project = {
          ...projectData,
          id: id2,
          status: "idle",
          progress: 0,
          createdAt: (/* @__PURE__ */ new Date()).toISOString()
        };
        set((state) => ({
          projects: [...state.projects, project],
          activeProjectId: id2
        }));
        return id2;
      },
      updateProject: (id2, updates) => {
        set((state) => ({
          projects: state.projects.map(
            (p2) => p2.id === id2 ? { ...p2, ...updates } : p2
          )
        }));
      },
      removeProject: (id2) => {
        const { stopProject, activeProjectId, previewProjectId } = get();
        stopProject(id2);
        set((state) => ({
          projects: state.projects.filter((p2) => p2.id !== id2),
          activeProjectId: activeProjectId === id2 ? null : activeProjectId,
          previewProjectId: previewProjectId === id2 ? null : previewProjectId
        }));
      },
      setActiveProject: async (id2) => {
        set({ activeProjectId: id2 });
        if (id2) {
          const project = get().projects.find((p2) => p2.id === id2);
          if (project?.outputDir && !get().previewProjectId) {
            try {
              const hasCode = await window.electronAPI.fs.exists(
                `${project.outputDir}/package.json`
              );
              if (hasCode) {
                console.log("[ProjectStore] Auto-starting preview for project with existing code:", id2);
                get().startPreviewOnly(id2);
              }
            } catch (error) {
              console.warn("[ProjectStore] Could not check for existing code:", error);
            }
          }
        }
      },
      setPreviewProject: (id2) => {
        set({ previewProjectId: id2 });
      },
      getProject: (id2) => {
        return get().projects.find((p2) => p2.id === id2);
      },
      // Start project container for live preview
      startProject: async (id2) => {
        const project = get().getProject(id2);
        if (!project) return false;
        try {
          set((state) => ({
            projects: state.projects.map(
              (p2) => p2.id === id2 ? { ...p2, status: "running" } : p2
            )
          }));
          const result = await window.electronAPI.docker.startProject(
            id2,
            project.requirementsPath,
            project.outputDir
          );
          if (result.success) {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? {
                  ...p2,
                  vncPort: result.vncPort,
                  appPort: result.appPort,
                  status: "running",
                  lastRunAt: (/* @__PURE__ */ new Date()).toISOString()
                } : p2
              ),
              previewProjectId: id2
            }));
            return true;
          } else {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? { ...p2, status: "error", error: result.error } : p2
              )
            }));
            return false;
          }
        } catch (error) {
          set((state) => ({
            projects: state.projects.map(
              (p2) => p2.id === id2 ? { ...p2, status: "error", error: error.message } : p2
            )
          }));
          return false;
        }
      },
      // Stop project container
      stopProject: async (id2) => {
        try {
          await window.electronAPI.docker.stopProject(id2);
          set((state) => ({
            projects: state.projects.map(
              (p2) => p2.id === id2 ? { ...p2, status: "stopped", vncPort: void 0, appPort: void 0 } : p2
            ),
            previewProjectId: state.previewProjectId === id2 ? null : state.previewProjectId
          }));
          return true;
        } catch (error) {
          console.error("Failed to stop project:", error);
          return false;
        }
      },
      // Start code generation WITH live VNC preview
      // forceGenerate: if true, always run generation even if project files exist
      startGeneration: async (id2, forceGenerate = false) => {
        const project = get().getProject(id2);
        if (!project) return false;
        try {
          set((state) => ({
            projects: state.projects.map(
              (p2) => p2.id === id2 ? { ...p2, status: "generating", progress: 0 } : p2
            )
          }));
          const result = await window.electronAPI.engine.startGenerationWithPreview(
            id2,
            project.requirementsPath,
            project.outputDir,
            forceGenerate
          );
          if (result.success) {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? {
                  ...p2,
                  status: "generating",
                  vncPort: result.vncPort,
                  appPort: result.appPort,
                  lastRunAt: (/* @__PURE__ */ new Date()).toISOString()
                } : p2
              ),
              // Automatically show the live preview
              previewProjectId: id2
            }));
          } else {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? { ...p2, status: "error", error: result.error } : p2
              )
            }));
          }
          return result.success;
        } catch (error) {
          set((state) => ({
            projects: state.projects.map(
              (p2) => p2.id === id2 ? { ...p2, status: "error", error: error.message } : p2
            )
          }));
          return false;
        }
      },
      // Stop a running generation (graceful: pauses epic orchestrator first, then kills container)
      stopGeneration: async (id2) => {
        try {
          try {
            await fetch("http://localhost:8000/api/v1/dashboard/stop-generation", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ project_id: id2 })
            });
          } catch (apiErr) {
            console.warn("[ProjectStore] Could not call stop-generation API (non-fatal):", apiErr);
          }
          await window.electronAPI.engine.stopGeneration(id2);
          try {
            const { useEngineStore: useEngineStore2 } = await __vitePreload(async () => {
              const { useEngineStore: useEngineStore3 } = await Promise.resolve().then(() => engineStore);
              return { useEngineStore: useEngineStore3 };
            }, true ? void 0 : void 0, import.meta.url);
            useEngineStore2.getState().generationProgress;
            useEngineStore2.setState({
              generationPhase: "Stopped"
            });
          } catch (_) {
          }
          set((state) => ({
            projects: state.projects.map(
              (p2) => p2.id === id2 ? { ...p2, status: "stopped", vncPort: void 0, appPort: void 0 } : p2
            ),
            previewProjectId: state.previewProjectId === id2 ? null : state.previewProjectId
          }));
          return true;
        } catch (error) {
          console.error("Failed to stop generation:", error);
          return false;
        }
      },
      // Start preview only (no generation) - for projects with existing code
      startPreviewOnly: async (id2) => {
        const project = get().projects.find((p2) => p2.id === id2);
        if (!project?.outputDir) {
          console.warn("[ProjectStore] Cannot start preview: no outputDir for project", id2);
          return false;
        }
        try {
          console.log("[ProjectStore] Starting preview-only for:", id2);
          const result = await window.electronAPI.docker.startProject(
            id2,
            project.requirementsPath || project.outputDir,
            project.outputDir
          );
          if (result.success) {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? {
                  ...p2,
                  status: "running",
                  vncPort: result.vncPort,
                  appPort: result.appPort,
                  lastRunAt: (/* @__PURE__ */ new Date()).toISOString()
                } : p2
              ),
              previewProjectId: id2
            }));
            console.log("[ProjectStore] Preview started on VNC port:", result.vncPort);
            return true;
          } else {
            console.error("[ProjectStore] Failed to start preview:", result.error);
            return false;
          }
        } catch (error) {
          console.error("[ProjectStore] Preview start error:", error);
          return false;
        }
      },
      // ========================================================================
      // Orchestrator Actions
      // ========================================================================
      /**
       * Load projects from req-orchestrator (port 8087)
       */
      loadFromOrchestrator: async () => {
        set({ orchestratorLoading: true, orchestratorError: null });
        try {
          const projects = await window.electronAPI.projects.getAll();
          set({
            orchestratorProjects: projects,
            orchestratorLoading: false
          });
          console.log(`[ProjectStore] Loaded ${projects.length} projects from orchestrator`);
          return true;
        } catch (error) {
          set({ orchestratorLoading: false });
          console.log("[ProjectStore] Orchestrator not available:", error.message);
          return false;
        }
      },
      /**
       * Toggle selection of an orchestrator project
       */
      toggleOrchestratorSelection: (projectId) => {
        set((state) => {
          const isSelected = state.selectedOrchestratorIds.includes(projectId);
          return {
            selectedOrchestratorIds: isSelected ? state.selectedOrchestratorIds.filter((id2) => id2 !== projectId) : [...state.selectedOrchestratorIds, projectId]
          };
        });
      },
      /**
       * Clear all orchestrator selections
       */
      clearOrchestratorSelection: () => {
        set({ selectedOrchestratorIds: [] });
      },
      /**
       * Generate from selected orchestrator projects WITH VNC preview
       * Starts VNC container for each project and shows live preview
       */
      generateFromOrchestrator: async () => {
        const { selectedOrchestratorIds, orchestratorProjects } = get();
        if (selectedOrchestratorIds.length === 0) {
          console.warn("[ProjectStore] No projects selected for generation");
          return false;
        }
        try {
          console.log(
            `[ProjectStore] Starting generation with VNC for ${selectedOrchestratorIds.length} projects:`,
            selectedOrchestratorIds
          );
          let firstSuccessfulProjectId = null;
          for (const projectId of selectedOrchestratorIds) {
            const orchestratorProject = orchestratorProjects.find(
              (p2) => p2.project_id === projectId
            );
            if (!orchestratorProject) {
              console.warn(`[ProjectStore] Orchestrator project not found: ${projectId}`);
              continue;
            }
            const outputDir = `./output_${projectId}`;
            console.log(
              `[ProjectStore] Starting generation for "${orchestratorProject.project_name}"`,
              { projectPath: orchestratorProject.project_path, outputDir }
            );
            const result = await window.electronAPI.engine.startOrchestratorGenerationWithPreview(
              projectId,
              orchestratorProject.project_path,
              outputDir
            );
            if (result.success) {
              console.log(
                `[ProjectStore] VNC started for ${projectId} on port ${result.vncPort}`
              );
              const newProject = {
                id: projectId,
                name: orchestratorProject.project_name,
                description: `Generated from orchestrator: ${orchestratorProject.template_name}`,
                requirementsPath: orchestratorProject.project_path,
                outputDir,
                status: "generating",
                progress: 0,
                vncPort: result.vncPort,
                appPort: result.appPort,
                createdAt: (/* @__PURE__ */ new Date()).toISOString(),
                lastRunAt: (/* @__PURE__ */ new Date()).toISOString()
              };
              set((state) => ({
                projects: [
                  ...state.projects.filter((p2) => p2.id !== projectId),
                  // Remove if exists
                  newProject
                ],
                previewProjectId: state.previewProjectId || projectId
                // Show first project's preview
              }));
              if (!firstSuccessfulProjectId) {
                firstSuccessfulProjectId = projectId;
              }
            } else {
              console.error(
                `[ProjectStore] Failed to start generation for ${projectId}:`,
                result.error
              );
              set({ orchestratorError: result.error || "Generation failed" });
            }
          }
          set({ selectedOrchestratorIds: [] });
          if (firstSuccessfulProjectId) {
            set({ previewProjectId: firstSuccessfulProjectId });
            console.log(
              `[ProjectStore] Generation started successfully, preview: ${firstSuccessfulProjectId}`
            );
            return true;
          }
          return false;
        } catch (error) {
          console.error("[ProjectStore] Generation error:", error);
          set({ orchestratorError: error.message || "Generation error" });
          return false;
        }
      },
      // =========================================================================
      // RE (Requirements Engineer) Project Actions
      // =========================================================================
      loadLocalREProjects: async (paths) => {
        set({ reProjectsLoading: true });
        try {
          const projects = await window.electronAPI.projects.scanLocalDirs(paths);
          set({ reProjects: projects, reProjectsLoading: false });
          console.log(`[ProjectStore] Loaded ${projects.length} local RE projects`);
          return true;
        } catch (error) {
          console.error("[ProjectStore] Failed to load RE projects:", error);
          set({ reProjectsLoading: false });
          return false;
        }
      },
      selectREProject: async (path) => {
        if (!path) {
          set({ selectedREProject: null });
          return;
        }
        try {
          const detail = await window.electronAPI.projects.getREDetail(path);
          set({ selectedREProject: detail });
        } catch (error) {
          console.error("[ProjectStore] Failed to load RE project detail:", error);
        }
      },
      generateFromREProject: async (projectPath) => {
        const { reProjects } = get();
        const reProject = reProjects.find((p2) => p2.project_path === projectPath);
        if (!reProject) return false;
        const projectId = `re-${reProject.project_id}`;
        const outputDir = `./output_${reProject.project_id}`;
        try {
          const newProject = {
            id: projectId,
            name: reProject.project_name,
            description: `RE Project: ${reProject.requirements_count} requirements, ${reProject.tasks_count} tasks`,
            requirementsPath: projectPath,
            outputDir,
            status: "generating",
            progress: 0,
            createdAt: (/* @__PURE__ */ new Date()).toISOString(),
            lastRunAt: (/* @__PURE__ */ new Date()).toISOString()
          };
          set((state) => ({
            projects: [
              ...state.projects.filter((p2) => p2.id !== projectId),
              newProject
            ],
            // Keep RE selection so REProjectDetailView stays visible with progress panel
            activeProjectId: projectId
          }));
          let result;
          if (reProject.user_stories_count > 0) {
            result = await window.electronAPI.engine.startEpicGeneration(
              projectId,
              projectPath,
              outputDir
            );
            if (result.success) {
              try {
                const { useEngineStore: useEngineStore2 } = await __vitePreload(async () => {
                  const { useEngineStore: useEngineStore3 } = await Promise.resolve().then(() => engineStore);
                  return { useEngineStore: useEngineStore3 };
                }, true ? void 0 : void 0, import.meta.url);
                useEngineStore2.getState().loadEpics(projectPath);
              } catch (e) {
                console.warn("[ProjectStore] Could not load epics into engineStore:", e);
              }
            }
          } else {
            result = await window.electronAPI.engine.startGenerationWithPreview(
              projectId,
              projectPath,
              outputDir,
              true
              // forceGenerate
            );
          }
          if (result.success) {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === projectId ? { ...p2, vncPort: result.vncPort, appPort: result.appPort } : p2
              ),
              previewProjectId: projectId,
              activeProjectId: projectId
            }));
            console.log(`[ProjectStore] RE generation started: ${reProject.project_name} on VNC port ${result.vncPort}`);
            return true;
          } else {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === projectId ? { ...p2, status: "error", error: result.error } : p2
              )
            }));
            return false;
          }
        } catch (error) {
          console.error("[ProjectStore] RE generation error:", error);
          return false;
        }
      },
      // =========================================================================
      // Review Gate Actions (Pause/Resume for User Review)
      // =========================================================================
      pauseForReview: async (id2) => {
        try {
          const response = await fetch(
            `http://localhost:8000/api/v1/dashboard/generation/${id2}/pause`,
            { method: "POST" }
          );
          if (response.ok) {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? { ...p2, status: "paused", reviewPaused: true } : p2
              )
            }));
            console.log("[ProjectStore] Generation paused for review:", id2);
            return true;
          }
          return false;
        } catch (error) {
          console.error("[ProjectStore] Failed to pause for review:", error);
          return false;
        }
      },
      resumeWithFeedback: async (id2, feedback) => {
        try {
          const response = await fetch(
            `http://localhost:8000/api/v1/dashboard/generation/${id2}/resume`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ feedback })
            }
          );
          if (response.ok) {
            set((state) => ({
              projects: state.projects.map(
                (p2) => p2.id === id2 ? { ...p2, status: "generating", reviewPaused: false, reviewFeedback: void 0 } : p2
              )
            }));
            console.log("[ProjectStore] Generation resumed:", id2, feedback ? "with feedback" : "");
            return true;
          }
          return false;
        } catch (error) {
          console.error("[ProjectStore] Failed to resume:", error);
          return false;
        }
      }
    }),
    {
      name: "coding-engine-projects",
      partialize: (state) => ({
        projects: state.projects,
        activeProjectId: state.activeProjectId
      }),
      // Custom storage to reset stuck "generating" states on load
      storage: {
        getItem: (name) => {
          const str = localStorage.getItem(name);
          if (!str) return null;
          try {
            const data = JSON.parse(str);
            if (data.state?.projects) {
              data.state.projects = data.state.projects.map(
                (p2) => p2.status === "generating" || p2.status === "paused" ? { ...p2, status: "idle", vncPort: void 0, appPort: void 0, progress: 0, reviewPaused: false } : p2
              );
              console.log("[ProjectStore] Reset stuck generating/paused states on load");
            }
            return data;
          } catch {
            return null;
          }
        },
        setItem: (name, value) => localStorage.setItem(name, JSON.stringify(value)),
        removeItem: (name) => localStorage.removeItem(name)
      }
    }
  )
);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
var defaultAttributes = {
  xmlns: "http://www.w3.org/2000/svg",
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round"
};
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const toKebabCase = (string) => string.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase().trim();
const createLucideIcon = (iconName, iconNode) => {
  const Component = reactExports.forwardRef(
    ({ color = "currentColor", size = 24, strokeWidth = 2, absoluteStrokeWidth, className = "", children, ...rest }, ref) => reactExports.createElement(
      "svg",
      {
        ref,
        ...defaultAttributes,
        width: size,
        height: size,
        stroke: color,
        strokeWidth: absoluteStrokeWidth ? Number(strokeWidth) * 24 / Number(size) : strokeWidth,
        className: ["lucide", `lucide-${toKebabCase(iconName)}`, className].join(" "),
        ...rest
      },
      [
        ...iconNode.map(([tag, attrs]) => reactExports.createElement(tag, attrs)),
        ...Array.isArray(children) ? children : [children]
      ]
    )
  );
  Component.displayName = `${iconName}`;
  return Component;
};
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Activity = createLucideIcon("Activity", [
  ["path", { d: "M22 12h-4l-3 9L9 3l-3 9H2", key: "d5dnw9" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const AlertCircle = createLucideIcon("AlertCircle", [
  ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
  ["line", { x1: "12", x2: "12", y1: "8", y2: "12", key: "1pkeuh" }],
  ["line", { x1: "12", x2: "12.01", y1: "16", y2: "16", key: "4dfq90" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const AlertTriangle = createLucideIcon("AlertTriangle", [
  [
    "path",
    {
      d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z",
      key: "c3ski4"
    }
  ],
  ["path", { d: "M12 9v4", key: "juzpu7" }],
  ["path", { d: "M12 17h.01", key: "p32p05" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ArrowLeft = createLucideIcon("ArrowLeft", [
  ["path", { d: "m12 19-7-7 7-7", key: "1l729n" }],
  ["path", { d: "M19 12H5", key: "x3x0zl" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ArrowRight = createLucideIcon("ArrowRight", [
  ["path", { d: "M5 12h14", key: "1ays0h" }],
  ["path", { d: "m12 5 7 7-7 7", key: "xquz4c" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Award = createLucideIcon("Award", [
  ["circle", { cx: "12", cy: "8", r: "6", key: "1vp47v" }],
  ["path", { d: "M15.477 12.89 17 22l-5-3-5 3 1.523-9.11", key: "em7aur" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const BarChart3 = createLucideIcon("BarChart3", [
  ["path", { d: "M3 3v18h18", key: "1s2lah" }],
  ["path", { d: "M18 17V9", key: "2bz60n" }],
  ["path", { d: "M13 17V5", key: "1frdt8" }],
  ["path", { d: "M8 17v-3", key: "17ska0" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const BookOpen = createLucideIcon("BookOpen", [
  ["path", { d: "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z", key: "vv98re" }],
  ["path", { d: "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z", key: "1cyq3y" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Bot = createLucideIcon("Bot", [
  ["path", { d: "M12 8V4H8", key: "hb8ula" }],
  ["rect", { width: "16", height: "12", x: "4", y: "8", rx: "2", key: "enze0r" }],
  ["path", { d: "M2 14h2", key: "vft8re" }],
  ["path", { d: "M20 14h2", key: "4cs60a" }],
  ["path", { d: "M15 13v2", key: "1xurst" }],
  ["path", { d: "M9 13v2", key: "rq6x2g" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Box = createLucideIcon("Box", [
  [
    "path",
    {
      d: "M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",
      key: "hh9hay"
    }
  ],
  ["path", { d: "m3.3 7 8.7 5 8.7-5", key: "g66t2b" }],
  ["path", { d: "M12 22V12", key: "d0xqtd" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Building2 = createLucideIcon("Building2", [
  ["path", { d: "M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z", key: "1b4qmf" }],
  ["path", { d: "M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2", key: "i71pzd" }],
  ["path", { d: "M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2", key: "10jefs" }],
  ["path", { d: "M10 6h4", key: "1itunk" }],
  ["path", { d: "M10 10h4", key: "tcdvrf" }],
  ["path", { d: "M10 14h4", key: "kelpxr" }],
  ["path", { d: "M10 18h4", key: "1ulq68" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Calendar = createLucideIcon("Calendar", [
  ["rect", { width: "18", height: "18", x: "3", y: "4", rx: "2", ry: "2", key: "eu3xkr" }],
  ["line", { x1: "16", x2: "16", y1: "2", y2: "6", key: "m3sa8f" }],
  ["line", { x1: "8", x2: "8", y1: "2", y2: "6", key: "18kwsl" }],
  ["line", { x1: "3", x2: "21", y1: "10", y2: "10", key: "xt86sb" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const CheckCircle2 = createLucideIcon("CheckCircle2", [
  ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
  ["path", { d: "m9 12 2 2 4-4", key: "dzmm74" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const CheckCircle = createLucideIcon("CheckCircle", [
  ["path", { d: "M22 11.08V12a10 10 0 1 1-5.93-9.14", key: "g774vq" }],
  ["path", { d: "m9 11 3 3L22 4", key: "1pflzl" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const CheckSquare = createLucideIcon("CheckSquare", [
  ["path", { d: "m9 11 3 3L22 4", key: "1pflzl" }],
  ["path", { d: "M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11", key: "1jnkn4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Check = createLucideIcon("Check", [["path", { d: "M20 6 9 17l-5-5", key: "1gmf2c" }]]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ChevronDown = createLucideIcon("ChevronDown", [
  ["path", { d: "m6 9 6 6 6-6", key: "qrunsl" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ChevronRight = createLucideIcon("ChevronRight", [
  ["path", { d: "m9 18 6-6-6-6", key: "mthhwq" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ChevronUp = createLucideIcon("ChevronUp", [["path", { d: "m18 15-6-6-6 6", key: "153udz" }]]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Clock = createLucideIcon("Clock", [
  ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
  ["polyline", { points: "12 6 12 12 16 14", key: "68esgv" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Code2 = createLucideIcon("Code2", [
  ["path", { d: "m18 16 4-4-4-4", key: "1inbqp" }],
  ["path", { d: "m6 8-4 4 4 4", key: "15zrgr" }],
  ["path", { d: "m14.5 4-5 16", key: "e7oirm" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Container = createLucideIcon("Container", [
  [
    "path",
    {
      d: "M22 7.7c0-.6-.4-1.2-.8-1.5l-6.3-3.9a1.72 1.72 0 0 0-1.7 0l-10.3 6c-.5.2-.9.8-.9 1.4v6.6c0 .5.4 1.2.8 1.5l6.3 3.9a1.72 1.72 0 0 0 1.7 0l10.3-6c.5-.3.9-1 .9-1.5Z",
      key: "1t2lqe"
    }
  ],
  ["path", { d: "M10 21.9V14L2.1 9.1", key: "o7czzq" }],
  ["path", { d: "m10 14 11.9-6.9", key: "zm5e20" }],
  ["path", { d: "M14 19.8v-8.1", key: "159ecu" }],
  ["path", { d: "M18 17.5V9.4", key: "11uown" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Cpu = createLucideIcon("Cpu", [
  ["rect", { x: "4", y: "4", width: "16", height: "16", rx: "2", key: "1vbyd7" }],
  ["rect", { x: "9", y: "9", width: "6", height: "6", key: "o3kz5p" }],
  ["path", { d: "M15 2v2", key: "13l42r" }],
  ["path", { d: "M15 20v2", key: "15mkzm" }],
  ["path", { d: "M2 15h2", key: "1gxd5l" }],
  ["path", { d: "M2 9h2", key: "1bbxkp" }],
  ["path", { d: "M20 15h2", key: "19e6y8" }],
  ["path", { d: "M20 9h2", key: "19tzq7" }],
  ["path", { d: "M9 2v2", key: "165o2o" }],
  ["path", { d: "M9 20v2", key: "i2bqo8" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Database = createLucideIcon("Database", [
  ["ellipse", { cx: "12", cy: "5", rx: "9", ry: "3", key: "msslwz" }],
  ["path", { d: "M3 5V19A9 3 0 0 0 21 19V5", key: "1wlel7" }],
  ["path", { d: "M3 12A9 3 0 0 0 21 12", key: "mv7ke4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Download = createLucideIcon("Download", [
  ["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", key: "ih7n3h" }],
  ["polyline", { points: "7 10 12 15 17 10", key: "2ggqvy" }],
  ["line", { x1: "12", x2: "12", y1: "15", y2: "3", key: "1vk2je" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ExternalLink = createLucideIcon("ExternalLink", [
  ["path", { d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6", key: "a6xqqp" }],
  ["polyline", { points: "15 3 21 3 21 9", key: "mznyad" }],
  ["line", { x1: "10", x2: "21", y1: "14", y2: "3", key: "18c3s4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Eye = createLucideIcon("Eye", [
  ["path", { d: "M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z", key: "rwhkz3" }],
  ["circle", { cx: "12", cy: "12", r: "3", key: "1v7zrd" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const FileJson = createLucideIcon("FileJson", [
  [
    "path",
    { d: "M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z", key: "1nnpy2" }
  ],
  ["polyline", { points: "14 2 14 8 20 8", key: "1ew0cm" }],
  [
    "path",
    { d: "M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1", key: "1oajmo" }
  ],
  [
    "path",
    { d: "M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1", key: "mpwhp6" }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const FileText = createLucideIcon("FileText", [
  [
    "path",
    { d: "M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z", key: "1nnpy2" }
  ],
  ["polyline", { points: "14 2 14 8 20 8", key: "1ew0cm" }],
  ["line", { x1: "16", x2: "8", y1: "13", y2: "13", key: "14keom" }],
  ["line", { x1: "16", x2: "8", y1: "17", y2: "17", key: "17nazh" }],
  ["line", { x1: "10", x2: "8", y1: "9", y2: "9", key: "1a5vjj" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Filter = createLucideIcon("Filter", [
  ["polygon", { points: "22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3", key: "1yg77f" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const FolderOpen = createLucideIcon("FolderOpen", [
  [
    "path",
    {
      d: "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2",
      key: "usdka0"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Folder = createLucideIcon("Folder", [
  [
    "path",
    {
      d: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z",
      key: "1kt360"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const GitBranch = createLucideIcon("GitBranch", [
  ["line", { x1: "6", x2: "6", y1: "3", y2: "15", key: "17qcm7" }],
  ["circle", { cx: "18", cy: "6", r: "3", key: "1h7g24" }],
  ["circle", { cx: "6", cy: "18", r: "3", key: "fqmcym" }],
  ["path", { d: "M18 9a9 9 0 0 1-9 9", key: "n2h4wq" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const GitFork = createLucideIcon("GitFork", [
  ["circle", { cx: "12", cy: "18", r: "3", key: "1mpf1b" }],
  ["circle", { cx: "6", cy: "6", r: "3", key: "1lh9wr" }],
  ["circle", { cx: "18", cy: "6", r: "3", key: "1h7g24" }],
  ["path", { d: "M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9", key: "1uq4wg" }],
  ["path", { d: "M12 12v3", key: "158kv8" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const HelpCircle = createLucideIcon("HelpCircle", [
  ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
  ["path", { d: "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3", key: "1u773s" }],
  ["path", { d: "M12 17h.01", key: "p32p05" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Image$1 = createLucideIcon("Image", [
  ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2", ry: "2", key: "1m3agn" }],
  ["circle", { cx: "9", cy: "9", r: "2", key: "af1f0g" }],
  ["path", { d: "m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21", key: "1xmnt7" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Layers = createLucideIcon("Layers", [
  [
    "path",
    {
      d: "m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z",
      key: "8b97xw"
    }
  ],
  ["path", { d: "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65", key: "dd6zsq" }],
  ["path", { d: "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65", key: "ep9fru" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Link2 = createLucideIcon("Link2", [
  ["path", { d: "M9 17H7A5 5 0 0 1 7 7h2", key: "8i5ue5" }],
  ["path", { d: "M15 7h2a5 5 0 1 1 0 10h-2", key: "1b9ql8" }],
  ["line", { x1: "8", x2: "16", y1: "12", y2: "12", key: "1jonct" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ListChecks = createLucideIcon("ListChecks", [
  ["path", { d: "m3 17 2 2 4-4", key: "1jhpwq" }],
  ["path", { d: "m3 7 2 2 4-4", key: "1obspn" }],
  ["path", { d: "M13 6h8", key: "15sg57" }],
  ["path", { d: "M13 12h8", key: "h98zly" }],
  ["path", { d: "M13 18h8", key: "oe0vm4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ListTodo = createLucideIcon("ListTodo", [
  ["rect", { x: "3", y: "5", width: "6", height: "6", rx: "1", key: "1defrl" }],
  ["path", { d: "m3 17 2 2 4-4", key: "1jhpwq" }],
  ["path", { d: "M13 6h8", key: "15sg57" }],
  ["path", { d: "M13 12h8", key: "h98zly" }],
  ["path", { d: "M13 18h8", key: "oe0vm4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Loader2 = createLucideIcon("Loader2", [
  ["path", { d: "M21 12a9 9 0 1 1-6.219-8.56", key: "13zald" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Lock = createLucideIcon("Lock", [
  ["rect", { width: "18", height: "11", x: "3", y: "11", rx: "2", ry: "2", key: "1w4ew1" }],
  ["path", { d: "M7 11V7a5 5 0 0 1 10 0v4", key: "fwvmzm" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Map$1 = createLucideIcon("Map", [
  ["polygon", { points: "3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21", key: "ok2ie8" }],
  ["line", { x1: "9", x2: "9", y1: "3", y2: "18", key: "w34qz5" }],
  ["line", { x1: "15", x2: "15", y1: "6", y2: "21", key: "volv9a" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Maximize2 = createLucideIcon("Maximize2", [
  ["polyline", { points: "15 3 21 3 21 9", key: "mznyad" }],
  ["polyline", { points: "9 21 3 21 3 15", key: "1avn1i" }],
  ["line", { x1: "21", x2: "14", y1: "3", y2: "10", key: "ota7mn" }],
  ["line", { x1: "3", x2: "10", y1: "21", y2: "14", key: "1atl0r" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const MessageSquare = createLucideIcon("MessageSquare", [
  ["path", { d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z", key: "1lielz" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Minimize2 = createLucideIcon("Minimize2", [
  ["polyline", { points: "4 14 10 14 10 20", key: "11kfnr" }],
  ["polyline", { points: "20 10 14 10 14 4", key: "rlmsce" }],
  ["line", { x1: "14", x2: "21", y1: "10", y2: "3", key: "o5lafz" }],
  ["line", { x1: "3", x2: "10", y1: "21", y2: "14", key: "1atl0r" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Monitor = createLucideIcon("Monitor", [
  ["rect", { width: "20", height: "14", x: "2", y: "3", rx: "2", key: "48i651" }],
  ["line", { x1: "8", x2: "16", y1: "21", y2: "21", key: "1svkeh" }],
  ["line", { x1: "12", x2: "12", y1: "17", y2: "21", key: "vw1qmm" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Package = createLucideIcon("Package", [
  ["path", { d: "m7.5 4.27 9 5.15", key: "1c824w" }],
  [
    "path",
    {
      d: "M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",
      key: "hh9hay"
    }
  ],
  ["path", { d: "m3.3 7 8.7 5 8.7-5", key: "g66t2b" }],
  ["path", { d: "M12 22V12", key: "d0xqtd" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Play = createLucideIcon("Play", [
  ["polygon", { points: "5 3 19 12 5 21 5 3", key: "191637" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Plus = createLucideIcon("Plus", [
  ["path", { d: "M5 12h14", key: "1ays0h" }],
  ["path", { d: "M12 5v14", key: "s699le" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const RefreshCw = createLucideIcon("RefreshCw", [
  ["path", { d: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", key: "v9h5vc" }],
  ["path", { d: "M21 3v5h-5", key: "1q7to0" }],
  ["path", { d: "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", key: "3uifl3" }],
  ["path", { d: "M8 16H3v5", key: "1cv678" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Rocket = createLucideIcon("Rocket", [
  [
    "path",
    {
      d: "M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z",
      key: "m3kijz"
    }
  ],
  [
    "path",
    {
      d: "m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z",
      key: "1fmvmk"
    }
  ],
  ["path", { d: "M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0", key: "1f8sc4" }],
  ["path", { d: "M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5", key: "qeys4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const RotateCcw = createLucideIcon("RotateCcw", [
  ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", key: "1357e3" }],
  ["path", { d: "M3 3v5h5", key: "1xhq8a" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Save = createLucideIcon("Save", [
  ["path", { d: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z", key: "1owoqh" }],
  ["polyline", { points: "17 21 17 13 7 13 7 21", key: "1md35c" }],
  ["polyline", { points: "7 3 7 8 15 8", key: "8nz8an" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Search = createLucideIcon("Search", [
  ["circle", { cx: "11", cy: "11", r: "8", key: "4ej97u" }],
  ["path", { d: "m21 21-4.3-4.3", key: "1qie3q" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Send = createLucideIcon("Send", [
  ["path", { d: "m22 2-7 20-4-9-9-4Z", key: "1q3vgg" }],
  ["path", { d: "M22 2 11 13", key: "nzbqef" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Server = createLucideIcon("Server", [
  ["rect", { width: "20", height: "8", x: "2", y: "2", rx: "2", ry: "2", key: "ngkwjq" }],
  ["rect", { width: "20", height: "8", x: "2", y: "14", rx: "2", ry: "2", key: "iecqi9" }],
  ["line", { x1: "6", x2: "6.01", y1: "6", y2: "6", key: "16zg32" }],
  ["line", { x1: "6", x2: "6.01", y1: "18", y2: "18", key: "nzw8ys" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Shield = createLucideIcon("Shield", [
  ["path", { d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10", key: "1irkt0" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const SkipForward = createLucideIcon("SkipForward", [
  ["polygon", { points: "5 4 15 12 5 20 5 4", key: "16p6eg" }],
  ["line", { x1: "19", x2: "19", y1: "5", y2: "19", key: "futhcm" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Square = createLucideIcon("Square", [
  ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2", key: "afitv7" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Star = createLucideIcon("Star", [
  [
    "polygon",
    {
      points: "12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2",
      key: "8f66p6"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Store = createLucideIcon("Store", [
  ["path", { d: "m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7", key: "ztvudi" }],
  ["path", { d: "M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8", key: "1b2hhj" }],
  ["path", { d: "M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4", key: "2ebpfo" }],
  ["path", { d: "M2 7h20", key: "1fcdvo" }],
  [
    "path",
    {
      d: "M22 7v3a2 2 0 0 1-2 2v0a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12v0a2 2 0 0 1-2-2V7",
      key: "jon5kx"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Terminal = createLucideIcon("Terminal", [
  ["polyline", { points: "4 17 10 11 4 5", key: "akl6gq" }],
  ["line", { x1: "12", x2: "20", y1: "19", y2: "19", key: "q2wloq" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const TestTube = createLucideIcon("TestTube", [
  ["path", { d: "M14.5 2v17.5c0 1.4-1.1 2.5-2.5 2.5h0c-1.4 0-2.5-1.1-2.5-2.5V2", key: "187lwq" }],
  ["path", { d: "M8.5 2h7", key: "csnxdl" }],
  ["path", { d: "M14.5 16h-5", key: "1ox875" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ThumbsDown = createLucideIcon("ThumbsDown", [
  ["path", { d: "M17 14V2", key: "8ymqnk" }],
  [
    "path",
    {
      d: "M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z",
      key: "s6e0r"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const ThumbsUp = createLucideIcon("ThumbsUp", [
  ["path", { d: "M7 10v12", key: "1qc93n" }],
  [
    "path",
    {
      d: "M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z",
      key: "y3tblf"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Trash2 = createLucideIcon("Trash2", [
  ["path", { d: "M3 6h18", key: "d0wm0j" }],
  ["path", { d: "M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6", key: "4alrt4" }],
  ["path", { d: "M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2", key: "v07s0e" }],
  ["line", { x1: "10", x2: "10", y1: "11", y2: "17", key: "1uufr5" }],
  ["line", { x1: "14", x2: "14", y1: "11", y2: "17", key: "xtxkd" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const TrendingUp = createLucideIcon("TrendingUp", [
  ["polyline", { points: "22 7 13.5 15.5 8.5 10.5 2 17", key: "126l90" }],
  ["polyline", { points: "16 7 22 7 22 13", key: "kwv8wd" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Unlock = createLucideIcon("Unlock", [
  ["rect", { width: "18", height: "11", x: "3", y: "11", rx: "2", ry: "2", key: "1w4ew1" }],
  ["path", { d: "M7 11V7a5 5 0 0 1 9.9-1", key: "1mm8w8" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Upload = createLucideIcon("Upload", [
  ["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", key: "ih7n3h" }],
  ["polyline", { points: "17 8 12 3 7 8", key: "t8dd8p" }],
  ["line", { x1: "12", x2: "12", y1: "3", y2: "15", key: "widbto" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const User = createLucideIcon("User", [
  ["path", { d: "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", key: "975kel" }],
  ["circle", { cx: "12", cy: "7", r: "4", key: "17ys0d" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const WifiOff = createLucideIcon("WifiOff", [
  ["line", { x1: "2", x2: "22", y1: "2", y2: "22", key: "a6p6uj" }],
  ["path", { d: "M8.5 16.5a5 5 0 0 1 7 0", key: "sej527" }],
  ["path", { d: "M2 8.82a15 15 0 0 1 4.17-2.65", key: "11utq1" }],
  ["path", { d: "M10.66 5c4.01-.36 8.14.9 11.34 3.76", key: "hxefdu" }],
  ["path", { d: "M16.85 11.25a10 10 0 0 1 2.22 1.68", key: "q734kn" }],
  ["path", { d: "M5 13a10 10 0 0 1 5.24-2.76", key: "piq4yl" }],
  ["line", { x1: "12", x2: "12.01", y1: "20", y2: "20", key: "of4bc4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Wifi = createLucideIcon("Wifi", [
  ["path", { d: "M5 13a10 10 0 0 1 14 0", key: "6v8j51" }],
  ["path", { d: "M8.5 16.5a5 5 0 0 1 7 0", key: "sej527" }],
  ["path", { d: "M2 8.82a15 15 0 0 1 20 0", key: "dnpr2z" }],
  ["line", { x1: "12", x2: "12.01", y1: "20", y2: "20", key: "of4bc4" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Wrench = createLucideIcon("Wrench", [
  [
    "path",
    {
      d: "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
      key: "cbrjhi"
    }
  ]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const XCircle = createLucideIcon("XCircle", [
  ["circle", { cx: "12", cy: "12", r: "10", key: "1mglay" }],
  ["path", { d: "m15 9-6 6", key: "1uzhvr" }],
  ["path", { d: "m9 9 6 6", key: "z0biqf" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const X = createLucideIcon("X", [
  ["path", { d: "M18 6 6 18", key: "1bl5f8" }],
  ["path", { d: "m6 6 12 12", key: "d8bk6v" }]
]);
/**
 * @license lucide-react v0.294.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */
const Zap = createLucideIcon("Zap", [
  ["polygon", { points: "13 2 3 14 12 14 11 22 21 10 12 10 13 2", key: "45s27k" }]
]);
function CreateProjectModal({ onClose }) {
  const { addProject } = useProjectStore();
  const [name, setName] = reactExports.useState("");
  const [description, setDescription] = reactExports.useState("");
  const [requirementsPath, setRequirementsPath] = reactExports.useState("");
  const [outputDir, setOutputDir] = reactExports.useState("");
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name || !requirementsPath || !outputDir) return;
    addProject({
      name,
      description,
      requirementsPath,
      outputDir
    });
    onClose();
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/50", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 w-full max-w-lg shadow-xl", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between p-4 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-semibold", children: "Create New Project" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: onClose,
          className: "p-1 hover:bg-gray-700 rounded transition",
          children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-5 h-5" })
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("form", { onSubmit: handleSubmit, className: "p-4 space-y-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm font-medium text-gray-300 mb-1", children: "Project Name *" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "input",
          {
            type: "text",
            value: name,
            onChange: (e) => setName(e.target.value),
            placeholder: "My Awesome App",
            className: "w-full px-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition",
            required: true
          }
        )
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm font-medium text-gray-300 mb-1", children: "Description" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "textarea",
          {
            value: description,
            onChange: (e) => setDescription(e.target.value),
            placeholder: "Brief description of the project...",
            rows: 2,
            className: "w-full px-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition resize-none"
          }
        )
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm font-medium text-gray-300 mb-1", children: "Requirements JSON Path *" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(FileJson, { className: "absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "input",
            {
              type: "text",
              value: requirementsPath,
              onChange: (e) => setRequirementsPath(e.target.value),
              placeholder: "C:\\path\\to\\requirements.json",
              className: "w-full pl-10 pr-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition",
              required: true
            }
          )
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-500 mt-1", children: "Path to the JSON file containing project requirements" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm font-medium text-gray-300 mb-1", children: "Output Directory *" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(FolderOpen, { className: "absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "input",
            {
              type: "text",
              value: outputDir,
              onChange: (e) => setOutputDir(e.target.value),
              placeholder: "C:\\path\\to\\output",
              className: "w-full pl-10 pr-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition",
              required: true
            }
          )
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-500 mt-1", children: "Directory where generated code will be saved" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-end gap-3 pt-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            type: "button",
            onClick: onClose,
            className: "px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition",
            children: "Cancel"
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            type: "submit",
            className: "px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition",
            children: "Create Project"
          }
        )
      ] })
    ] })
  ] }) });
}
function ProjectList() {
  const {
    orchestratorProjects,
    selectedOrchestratorIds,
    orchestratorLoading,
    toggleOrchestratorSelection,
    loadFromOrchestrator,
    setActiveProject,
    // RE projects
    reProjects,
    reProjectsLoading,
    loadLocalREProjects,
    selectREProject,
    selectedREProject
  } = useProjectStore();
  const [showCreateModal, setShowCreateModal] = reactExports.useState(false);
  const [reExpanded, setReExpanded] = reactExports.useState(true);
  const [orchExpanded, setOrchExpanded] = reactExports.useState(true);
  reactExports.useEffect(() => {
    loadLocalREProjects();
    loadFromOrchestrator();
  }, [loadLocalREProjects, loadFromOrchestrator]);
  const handleProjectClick = (project) => {
    setActiveProject(project.project_id);
  };
  const handleREProjectClick = (project) => {
    selectREProject(project.project_path);
  };
  const handleSelectToggle = (e, projectId) => {
    e.stopPropagation();
    toggleOrchestratorSelection(projectId);
  };
  const isSelected = (projectId) => selectedOrchestratorIds.includes(projectId);
  const isLoading = reProjectsLoading || orchestratorLoading;
  const handleRefresh = () => {
    loadLocalREProjects();
    loadFromOrchestrator();
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col h-full", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-3 border-b border-gray-700 flex items-center justify-between", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "font-semibold text-sm text-gray-300", children: "Projects" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: handleRefresh,
            className: "p-1.5 hover:bg-gray-700 rounded transition",
            title: "Refresh Projects",
            disabled: isLoading,
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(RefreshCw, { className: `w-4 h-4 ${isLoading ? "animate-spin" : ""}` })
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: () => setShowCreateModal(true),
            className: "p-1.5 hover:bg-gray-700 rounded transition",
            title: "New Project",
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-4 h-4" })
          }
        )
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => setReExpanded(!reExpanded),
            className: "w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:bg-gray-800/50 transition",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
                reExpanded ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-3 h-3" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-3 h-3" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: "Local (RE)" })
              ] }),
              reProjects.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded", children: reProjects.length })
            ]
          }
        ),
        reExpanded && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { children: reProjectsLoading && reProjects.length === 0 ? /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 py-2 text-center text-gray-500 text-xs", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin mx-auto mb-1" }),
          "Scanning..."
        ] }) : reProjects.length === 0 ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "px-4 py-2 text-gray-500 text-xs", children: "No RE projects in Data/all_services/" }) : /* @__PURE__ */ jsxRuntimeExports.jsx("ul", { className: "px-2 pb-1 space-y-0.5", children: reProjects.map((project) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "li",
          {
            onClick: () => handleREProjectClick(project),
            className: `
                        group flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition text-sm
                        ${selectedREProject?.project_path === project.project_path ? "bg-blue-500/20 border border-blue-500/50" : "hover:bg-gray-700/50"}
                      `,
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-4 h-4 text-blue-400 shrink-0" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "flex-1 truncate", children: project.project_name }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs bg-gray-700 px-1.5 py-0.5 rounded text-gray-400", children: project.requirements_count })
            ]
          },
          project.project_id
        )) }) })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => setOrchExpanded(!orchExpanded),
            className: "w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:bg-gray-800/50 transition",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
                orchExpanded ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-3 h-3" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-3 h-3" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: "Orchestrator" })
              ] }),
              orchestratorProjects.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs bg-gray-600 text-gray-300 px-1.5 py-0.5 rounded", children: orchestratorProjects.length })
            ]
          }
        ),
        orchExpanded && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { children: orchestratorLoading && orchestratorProjects.length === 0 ? /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 py-2 text-center text-gray-500 text-xs", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin mx-auto mb-1" }),
          "Connecting..."
        ] }) : orchestratorProjects.length === 0 ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "px-4 py-2 text-gray-500 text-xs", children: "Not connected (port 8087)" }) : /* @__PURE__ */ jsxRuntimeExports.jsx("ul", { className: "px-2 pb-1 space-y-0.5", children: orchestratorProjects.map((project) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "li",
          {
            onClick: () => handleProjectClick(project),
            className: `
                        group flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition text-sm
                        ${isSelected(project.project_id) ? "bg-engine-primary/20 border border-engine-primary/50" : "hover:bg-gray-700/50"}
                      `,
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: (e) => handleSelectToggle(e, project.project_id),
                  className: `
                          w-4 h-4 rounded border shrink-0 flex items-center justify-center transition
                          ${isSelected(project.project_id) ? "bg-engine-primary border-engine-primary" : "border-gray-500 hover:border-gray-400"}
                        `,
                  children: isSelected(project.project_id) && /* @__PURE__ */ jsxRuntimeExports.jsx(Check, { className: "w-3 h-3 text-white" })
                }
              ),
              /* @__PURE__ */ jsxRuntimeExports.jsx(Folder, { className: "w-4 h-4 text-gray-400 shrink-0" }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm font-medium truncate", children: project.project_name }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-500 truncate", children: project.template_name })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs bg-gray-700 px-1.5 py-0.5 rounded text-gray-400", children: project.requirements_count })
            ]
          },
          project.project_id
        )) }) })
      ] })
    ] }),
    selectedOrchestratorIds.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-2 border-t border-gray-700 text-xs text-gray-400", children: [
      selectedOrchestratorIds.length,
      " selected"
    ] }),
    showCreateModal && /* @__PURE__ */ jsxRuntimeExports.jsx(CreateProjectModal, { onClose: () => setShowCreateModal(false) })
  ] });
}
function ProjectCard({
  project,
  onStartGeneration,
  onStartPreview,
  onStopPreview
}) {
  const formatDate2 = (dateString) => {
    if (!dateString) return "Never";
    return new Date(dateString).toLocaleString();
  };
  const openInExplorer = (path) => {
    window.electronAPI.fs.showInExplorer(path);
  };
  const openFolder = (path) => {
    window.electronAPI.fs.openFolder(path);
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 overflow-hidden", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 border-b border-gray-700 flex items-center justify-between", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-xl font-semibold", children: project.name }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400 mt-1", children: project.description })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatusBadge$1, { status: project.status, progress: project.progress })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 space-y-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "text-xs text-gray-500 uppercase tracking-wider", children: "Requirements" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs(
            "button",
            {
              onClick: () => openInExplorer(project.requirementsPath),
              className: "mt-1 flex items-center gap-2 text-sm text-gray-300 hover:text-white transition group",
              children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(FileJson, { className: "w-4 h-4 text-blue-400" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "truncate", children: project.requirementsPath }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-3 h-3 opacity-0 group-hover:opacity-100" })
              ]
            }
          )
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "text-xs text-gray-500 uppercase tracking-wider", children: "Output Directory" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs(
            "button",
            {
              onClick: () => openFolder(project.outputDir),
              className: "mt-1 flex items-center gap-2 text-sm text-gray-300 hover:text-white transition group",
              children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(FolderOpen, { className: "w-4 h-4 text-yellow-400" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "truncate", children: project.outputDir }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-3 h-3 opacity-0 group-hover:opacity-100" })
              ]
            }
          )
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-4 text-sm", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-gray-400", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-4 h-4" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            "Created: ",
            formatDate2(project.createdAt)
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-gray-400", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-4 h-4" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            "Last Run: ",
            formatDate2(project.lastRunAt)
          ] })
        ] })
      ] }),
      (project.vncPort || project.appPort) && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-4 text-sm", children: [
        project.vncPort && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-3 py-1 bg-purple-500/20 text-purple-400 rounded", children: [
          "VNC: localhost:",
          project.vncPort
        ] }),
        project.appPort && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-3 py-1 bg-green-500/20 text-green-400 rounded", children: [
          "App: localhost:",
          project.appPort
        ] })
      ] }),
      project.error && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-400", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(AlertCircle, { className: "w-4 h-4 mt-0.5 shrink-0" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: project.error })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 border-t border-gray-700 flex gap-3", children: [
      project.status === "generating" ? /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          disabled: true,
          className: "flex items-center gap-2 px-4 py-2 bg-gray-600 rounded text-sm font-medium cursor-not-allowed",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }),
            "Generating... ",
            project.progress,
            "%"
          ]
        }
      ) : /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: onStartGeneration,
          className: "flex items-center gap-2 px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Rocket, { className: "w-4 h-4" }),
            "Generate Code"
          ]
        }
      ),
      project.status === "running" ? /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: onStopPreview,
          className: "flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-sm font-medium transition",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Square, { className: "w-4 h-4" }),
            "Stop Preview"
          ]
        }
      ) : /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: onStartPreview,
          disabled: project.status === "generating",
          className: "flex items-center gap-2 px-4 py-2 bg-engine-secondary hover:bg-emerald-600 rounded text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Eye, { className: "w-4 h-4" }),
            "Live Preview"
          ]
        }
      )
    ] })
  ] });
}
function StatusBadge$1({ status, progress }) {
  const config = {
    idle: { bg: "bg-gray-500/20", text: "text-gray-400", label: "Idle" },
    generating: { bg: "bg-yellow-500/20", text: "text-yellow-400", label: `Generating ${progress}%` },
    running: { bg: "bg-green-500/20", text: "text-green-400", label: "Running" },
    stopped: { bg: "bg-gray-500/20", text: "text-gray-400", label: "Stopped" },
    error: { bg: "bg-red-500/20", text: "text-red-400", label: "Error" }
  };
  const { bg: bg2, text, label } = config[status];
  return /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `px-3 py-1 rounded-full text-sm font-medium ${bg2} ${text}`, children: label });
}
const techColors = {
  // Frontend
  "React": { bg: "bg-blue-500/20", text: "text-blue-400" },
  "Vue.js": { bg: "bg-green-500/20", text: "text-green-400" },
  "Angular": { bg: "bg-red-500/20", text: "text-red-400" },
  "TypeScript": { bg: "bg-blue-600/20", text: "text-blue-300" },
  "Tailwind CSS": { bg: "bg-cyan-500/20", text: "text-cyan-400" },
  // Backend
  "FastAPI": { bg: "bg-teal-500/20", text: "text-teal-400" },
  "Python": { bg: "bg-yellow-500/20", text: "text-yellow-400" },
  "Python 3.11+": { bg: "bg-yellow-500/20", text: "text-yellow-400" },
  "Node.js": { bg: "bg-green-600/20", text: "text-green-300" },
  "Express": { bg: "bg-gray-500/20", text: "text-gray-300" },
  // Database
  "PostgreSQL": { bg: "bg-blue-700/20", text: "text-blue-300" },
  "SQLite": { bg: "bg-blue-400/20", text: "text-blue-300" },
  "SQLAlchemy": { bg: "bg-orange-500/20", text: "text-orange-400" },
  "SQLAlchemy 2.0": { bg: "bg-orange-500/20", text: "text-orange-400" },
  "MongoDB": { bg: "bg-green-700/20", text: "text-green-300" },
  "Prisma": { bg: "bg-indigo-500/20", text: "text-indigo-400" },
  // Tools
  "Docker": { bg: "bg-blue-500/20", text: "text-blue-400" },
  "Alembic": { bg: "bg-purple-500/20", text: "text-purple-400" },
  "Pydantic v2": { bg: "bg-pink-500/20", text: "text-pink-400" },
  "JWT": { bg: "bg-amber-500/20", text: "text-amber-400" },
  "Redis": { bg: "bg-red-600/20", text: "text-red-400" },
  "GraphQL": { bg: "bg-pink-600/20", text: "text-pink-400" },
  // Default
  "default": { bg: "bg-gray-500/20", text: "text-gray-400" }
};
function getTechColor(tech) {
  return techColors[tech] || techColors["default"];
}
function OrchestratorProjectCard({
  project,
  isSelected,
  onToggleSelect,
  onGenerate
}) {
  const formatDate2 = (dateString) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  };
  const { validation_summary } = project;
  const hasValidation = validation_summary.total > 0;
  const validationRate = hasValidation ? Math.round(validation_summary.passed / validation_summary.total * 100) : 0;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: `
        bg-engine-dark rounded-lg border overflow-hidden transition-all
        ${isSelected ? "border-engine-primary ring-2 ring-engine-primary/30" : "border-gray-700 hover:border-gray-600"}
      `,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 border-b border-gray-700 flex items-start gap-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: onToggleSelect,
              className: "mt-0.5 shrink-0 text-gray-400 hover:text-white transition",
              children: isSelected ? /* @__PURE__ */ jsxRuntimeExports.jsx(CheckSquare, { className: "w-5 h-5 text-engine-primary" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Square, { className: "w-5 h-5" })
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "font-semibold text-white truncate", children: project.project_name }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 mt-1 text-sm text-gray-400", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-3.5 h-3.5" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: project.template_name }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-600", children: "|" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "px-1.5 py-0.5 bg-gray-700 rounded text-xs", children: project.template_category })
            ] })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-4 border-b border-gray-700", children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5", children: project.tech_stack.map((tech) => {
          const { bg: bg2, text } = getTechColor(tech);
          return /* @__PURE__ */ jsxRuntimeExports.jsx(
            "span",
            {
              className: `px-2 py-0.5 text-xs font-medium rounded ${bg2} ${text}`,
              children: tech
            },
            tech
          );
        }) }) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 grid grid-cols-3 gap-4 text-sm", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-gray-400", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-4 h-4" }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
              project.requirements_count,
              " reqs"
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
            hasValidation ? validationRate === 100 ? /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-4 h-4 text-green-400" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-4 h-4 text-yellow-400" }) : /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "w-4 h-4" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: hasValidation ? validationRate === 100 ? "text-green-400" : "text-yellow-400" : "text-gray-500", children: hasValidation ? `${validationRate}% valid` : "Not validated" })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-gray-400 justify-end", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Calendar, { className: "w-4 h-4" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: formatDate2(project.created_at) })
          ] })
        ] }),
        project.source_file && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "px-4 pb-4", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
          "Source: ",
          project.source_file
        ] }) }),
        isSelected && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-4 border-t border-gray-700", children: /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: onGenerate,
            className: "w-full flex items-center justify-center gap-2 px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Rocket, { className: "w-4 h-4" }),
              "Generate Code"
            ]
          }
        ) })
      ]
    }
  );
}
function OrchestratorProjectsPanel() {
  const {
    orchestratorProjects,
    selectedOrchestratorIds,
    orchestratorLoading,
    orchestratorError,
    loadFromOrchestrator,
    toggleOrchestratorSelection,
    clearOrchestratorSelection,
    generateFromOrchestrator
  } = useProjectStore();
  const selectedCount = selectedOrchestratorIds.length;
  const hasSelection = selectedCount > 0;
  const handleGenerateSelected = async () => {
    const success = await generateFromOrchestrator();
    if (success) {
      console.log("Generation started for selected projects");
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 border-b border-gray-700 flex items-center justify-between", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Package, { className: "w-5 h-5 text-engine-primary" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-semibold", children: "Orchestrator Projects" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "px-2 py-0.5 bg-gray-700 rounded text-sm text-gray-400", children: [
          orchestratorProjects.length,
          " projects"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
        hasSelection && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: clearOrchestratorSelection,
              className: "text-sm text-gray-400 hover:text-white transition",
              children: "Clear Selection"
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-600", children: "|" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-sm text-engine-primary flex items-center gap-1", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(CheckSquare, { className: "w-4 h-4" }),
            selectedCount,
            " selected"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => loadFromOrchestrator(),
            disabled: orchestratorLoading,
            className: "flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm transition disabled:opacity-50",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(RefreshCw, { className: `w-4 h-4 ${orchestratorLoading ? "animate-spin" : ""}` }),
              "Refresh"
            ]
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: handleGenerateSelected,
            disabled: !hasSelection || orchestratorLoading,
            className: "flex items-center gap-2 px-4 py-1.5 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Rocket, { className: "w-4 h-4" }),
              "Generate ",
              hasSelection ? `(${selectedCount})` : ""
            ]
          }
        )
      ] })
    ] }),
    orchestratorError && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mx-4 mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded flex items-center gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(AlertCircle, { className: "w-5 h-5 text-red-400 shrink-0" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1", children: /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-red-400", children: orchestratorError }) }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: () => loadFromOrchestrator(),
          className: "text-sm text-red-400 hover:text-red-300 underline",
          children: "Retry"
        }
      )
    ] }),
    orchestratorLoading && orchestratorProjects.length === 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 flex items-center justify-center", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-12 h-12 mx-auto mb-4 text-engine-primary animate-spin" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-400", children: "Loading projects from orchestrator..." })
    ] }) }),
    !orchestratorLoading && orchestratorProjects.length === 0 && !orchestratorError && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 flex items-center justify-center", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Package, { className: "w-16 h-16 mx-auto mb-4 text-gray-600" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-lg text-gray-400", children: "No projects found" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-500 mt-2", children: "Make sure req-orchestrator is running on port 8087" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: () => loadFromOrchestrator(),
          className: "mt-4 px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm transition",
          children: "Load Projects"
        }
      )
    ] }) }),
    orchestratorProjects.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-auto p-4", children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4", children: orchestratorProjects.map((project) => /* @__PURE__ */ jsxRuntimeExports.jsx(
      OrchestratorProjectCard,
      {
        project,
        isSelected: selectedOrchestratorIds.includes(project.project_id),
        onToggleSelect: () => toggleOrchestratorSelection(project.project_id),
        onGenerate: handleGenerateSelected
      },
      project.project_id
    )) }) }),
    orchestratorProjects.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-3 border-t border-gray-700 text-center text-sm text-gray-500", children: 'Select projects and click "Generate" to send them to the Coding Engine for code generation' })
  ] });
}
let ws = null;
const useEngineStore = create((set, get) => ({
  // Initial state
  engineRunning: false,
  engineServices: [],
  wsConnected: false,
  wsEvents: [],
  generationProgress: 0,
  generationPhase: "idle",
  agentActivity: [],
  logs: [],
  taskChunks: [],
  taskProgress: { completed: 0, running: 0, failed: 0, pending: 0, total: 0, percent_complete: 0 },
  taskClarifications: [],
  epics: [],
  selectedEpic: null,
  epicTaskLists: {},
  loadEpicsLoading: false,
  currentProjectPath: null,
  vncUrl: null,
  vncPort: null,
  projectProfile: null,
  toasts: [],
  apiUrl: "http://localhost:8000",
  // Check engine status via IPC
  checkEngineStatus: async () => {
    try {
      const status = await window.electronAPI.docker.getEngineStatus();
      set({
        engineRunning: status.running,
        engineServices: status.services
      });
    } catch (error) {
      console.error("Failed to check engine status:", error);
    }
  },
  // Start engine
  startEngine: async () => {
    try {
      const result = await window.electronAPI.docker.startEngine();
      if (result.success) {
        set({ engineRunning: true });
        setTimeout(() => get().connectWebSocket(), 2e3);
      }
      return result.success;
    } catch (error) {
      console.error("Failed to start engine:", error);
      return false;
    }
  },
  // Stop engine
  stopEngine: async () => {
    try {
      get().disconnectWebSocket();
      const result = await window.electronAPI.docker.stopEngine();
      if (result.success) {
        set({ engineRunning: false, engineServices: [] });
      }
      return result.success;
    } catch (error) {
      console.error("Failed to stop engine:", error);
      return false;
    }
  },
  // Connect to Engine WebSocket
  connectWebSocket: () => {
    const { wsConnected, apiUrl } = get();
    if (wsConnected || ws) return;
    try {
      const wsUrl = apiUrl.replace(/^http/, "ws") + "/api/v1/ws";
      console.log("Connecting to WebSocket:", wsUrl);
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        console.log("WebSocket connected");
        set({ wsConnected: true });
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          get().addEvent({
            type: data.type,
            data: data.data,
            timestamp: data.timestamp || (/* @__PURE__ */ new Date()).toISOString()
          });
          if (data.type === "CONVERGENCE_UPDATE") {
            set({
              generationProgress: data.data?.progress || 0,
              generationPhase: data.data?.phase || "unknown"
            });
          } else if (data.type === "AGENT_STATUS") {
            const activity = get().agentActivity;
            const newEntry = {
              agent: data.data?.agent || data.data?.source || "Unknown",
              action: data.data?.action || data.data?.message || "",
              timestamp: data.timestamp || (/* @__PURE__ */ new Date()).toISOString(),
              status: data.data?.status || "running"
            };
            set({
              agentActivity: [...activity.slice(-49), newEntry]
            });
          } else if (data.type === "REVIEW_PAUSED" || data.type === "review_paused") {
            const projectId = data.data?.project_id;
            if (projectId) {
              useProjectStore.getState().updateProject(projectId, {
                status: "paused",
                reviewPaused: true
              });
            }
            console.log("[WebSocket] Generation paused for review:", projectId);
          } else if (data.type === "REVIEW_RESUMED" || data.type === "review_resumed") {
            const projectId = data.data?.project_id;
            if (projectId) {
              useProjectStore.getState().updateProject(projectId, {
                status: "generating",
                reviewPaused: false
              });
            }
            console.log("[WebSocket] Generation resumed:", projectId);
          }
          if (data.type === "vnc_preview_ready") {
            const payload = data.data || data;
            set({
              vncUrl: payload.url || null,
              vncPort: payload.port || null,
              projectProfile: payload.project_profile || null
            });
            console.log("[WebSocket] VNC preview ready:", payload.url, "profile:", payload.project_profile?.project_type);
          }
          const eventType = data.data?.event_type || data.data?.type || data.type;
          if (eventType === "task_progress_update") {
            const payload = data.data?.data || data.data;
            if (payload?.type === "plan_created" && payload.plan?.chunks) {
              set({
                taskChunks: payload.plan.chunks.map((c) => ({
                  chunk_id: c.chunk_id || c.id || "",
                  requirements: c.requirements || [],
                  service_group: c.service_group || "",
                  complexity: c.complexity || "medium",
                  status: c.status || "pending",
                  wave_id: c.wave_id ?? null,
                  estimated_minutes: c.estimated_minutes || 0,
                  error_message: c.error_message || null
                })),
                taskProgress: payload.progress || { completed: 0, running: 0, failed: 0, pending: 0, total: 0, percent_complete: 0 }
              });
            } else if (payload?.type === "batch_started" && payload.slice_ids) {
              set((state) => ({
                taskChunks: state.taskChunks.map(
                  (c) => payload.slice_ids.includes(c.chunk_id) ? { ...c, status: "running" } : c
                )
              }));
            } else if (payload?.type === "batch_completed") {
              set((state) => ({
                taskChunks: state.taskChunks.map((c) => {
                  if (payload.completed_slices?.includes(c.chunk_id)) return { ...c, status: "completed" };
                  if (payload.failed_slices?.includes(c.chunk_id)) return { ...c, status: "failed" };
                  return c;
                })
              }));
            } else if (payload?.type === "task_status_changed") {
              const { epic_id, task_id, status, error, tested } = payload;
              if (epic_id && task_id && status) {
                get().updateEpicTaskStatus(epic_id, task_id, status, error);
                if (tested !== void 0) {
                  set((state) => {
                    const taskList = state.epicTaskLists[epic_id];
                    if (!taskList) return state;
                    return {
                      epicTaskLists: {
                        ...state.epicTaskLists,
                        [epic_id]: {
                          ...taskList,
                          tasks: taskList.tasks.map(
                            (t2) => t2.id === task_id ? { ...t2, tested: !!tested } : t2
                          )
                        }
                      }
                    };
                  });
                }
                if (status === "failed") {
                  const taskList = get().epicTaskLists[epic_id];
                  const task = taskList?.tasks.find((t2) => t2.id === task_id);
                  get().addToast({
                    type: "error",
                    title: `Task Failed: ${task?.title || task_id}`,
                    message: error || "Task execution failed",
                    taskId: task_id,
                    epicId: epic_id
                  });
                }
              }
            } else if (payload?.type === "epic_status_changed") {
              const { epic_id, status, progress } = payload;
              if (epic_id && status) {
                get().updateEpicStatus(epic_id, status, progress);
                if (typeof progress === "number") {
                  set({ generationProgress: progress });
                }
                if (status === "running") {
                  set({ generationPhase: "Generating Code" });
                } else if (status === "completed") {
                  set({ generationProgress: 100, generationPhase: "Complete" });
                  useProjectStore.getState().projects.forEach((p2) => {
                    if (p2.status === "generating") {
                      useProjectStore.getState().updateProject(p2.id, { status: "running", progress: 100 });
                    }
                  });
                } else if (status === "failed") {
                  set({ generationPhase: "Failed" });
                }
              }
            } else if (payload?.type === "pipeline_progress") {
              const { completed, failed, total, running_ids, skipped } = payload;
              const pctComplete = total > 0 ? Math.round(completed / total * 100) : 0;
              set({
                generationProgress: pctComplete,
                generationPhase: `Generating Code (${completed}/${total} tasks)`,
                taskProgress: {
                  completed: completed || 0,
                  running: running_ids?.length || 0,
                  failed: failed || 0,
                  pending: Math.max(0, (total || 0) - (completed || 0) - (failed || 0) - (skipped || 0) - (running_ids?.length || 0)),
                  total: total || 0,
                  percent_complete: pctComplete
                }
              });
            } else if (payload?.type === "epic_execution_started") {
              set({
                generationProgress: 1,
                generationPhase: `Starting Epic: ${payload.epic_id} (${payload.total_tasks} tasks)`
              });
            } else if (payload?.type === "epic_execution_completed") {
              const result = payload.result || {};
              const pct = result.success ? 100 : get().generationProgress;
              set({
                generationProgress: pct,
                generationPhase: result.success ? "Complete" : `Done (${result.failed_tasks || 0} failures)`
              });
              useProjectStore.getState().projects.forEach((p2) => {
                if (p2.status === "generating") {
                  useProjectStore.getState().updateProject(p2.id, {
                    status: result.success ? "running" : "error",
                    progress: pct
                  });
                }
              });
            } else if (payload?.type === "log_entry") {
              const logMsg = payload.message || "";
              if (logMsg) {
                set((state) => ({
                  logs: [...state.logs.slice(-999), logMsg]
                }));
              }
            }
            const chunks = get().taskChunks;
            if (chunks.length > 0) {
              const completed = chunks.filter((c) => c.status === "completed").length;
              set({
                taskProgress: {
                  completed,
                  running: chunks.filter((c) => c.status === "running").length,
                  failed: chunks.filter((c) => c.status === "failed").length,
                  pending: chunks.filter((c) => c.status === "pending").length,
                  total: chunks.length,
                  percent_complete: completed / chunks.length * 100
                }
              });
            }
          }
          if (eventType === "clarification_requested") {
            const payload = data.data?.data || data.data;
            if (payload?.action === "enqueued" && payload.clarification) {
              set((state) => ({
                taskClarifications: [...state.taskClarifications, payload.clarification]
              }));
            }
          }
          if (eventType === "clarification_choice_submitted") {
            const payload = data.data?.data || data.data;
            if (payload?.action === "resolved" && payload.clarification_id) {
              set((state) => ({
                taskClarifications: state.taskClarifications.filter(
                  (c) => c.id !== payload.clarification_id
                )
              }));
            }
          }
          if (eventType === "clarification_timeout") {
            const payload = data.data?.data || data.data;
            if (payload?.clarification_id) {
              set((state) => ({
                taskClarifications: state.taskClarifications.filter(
                  (c) => c.id !== payload.clarification_id
                )
              }));
            }
          }
          if (data.type === "CHECKPOINT_REACHED" || eventType === "CHECKPOINT_REACHED") {
            const payload = data.data || data;
            console.log("[WebSocket] Checkpoint reached:", payload);
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };
      ws.onclose = () => {
        console.log("WebSocket disconnected");
        set({ wsConnected: false });
        ws = null;
        if (get().engineRunning) {
          setTimeout(() => get().connectWebSocket(), 5e3);
        }
      };
      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
      };
    } catch (error) {
      console.error("Failed to connect WebSocket:", error);
    }
  },
  // Disconnect WebSocket
  disconnectWebSocket: () => {
    if (ws) {
      ws.close();
      ws = null;
    }
    set({ wsConnected: false });
  },
  // Add event to history
  addEvent: (event) => {
    set((state) => ({
      wsEvents: [...state.wsEvents.slice(-99), event]
    }));
  },
  // Clear events
  clearEvents: () => {
    set({ wsEvents: [] });
  },
  // Load epics from project
  loadEpics: async (projectPath) => {
    console.log(`[EngineStore:loadEpics] Called with projectPath=${projectPath}`);
    set({ loadEpicsLoading: true });
    try {
      let epics = [];
      const hasIPC = !!window.electronAPI?.engine?.getEpics;
      console.log(`[EngineStore:loadEpics] IPC available=${hasIPC}`);
      if (hasIPC) {
        const result = await window.electronAPI.engine.getEpics(projectPath);
        console.log(`[EngineStore:loadEpics] IPC result:`, {
          epicCount: result?.epics?.length ?? 0,
          keys: result ? Object.keys(result) : "null",
          totalEpics: result?.total_epics ?? "N/A"
        });
        if (result?.epics?.length > 0) {
          epics = result.epics;
        }
      }
      if (epics.length === 0) {
        const { apiUrl } = get();
        console.log(`[EngineStore:loadEpics] Trying direct API: ${apiUrl}/api/v1/dashboard/epics`);
        const response = await fetch(`${apiUrl}/api/v1/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`);
        if (response.ok) {
          const data = await response.json();
          console.log(`[EngineStore:loadEpics] API result: ${data.epics?.length ?? 0} epics`);
          epics = data.epics || [];
        } else {
          console.warn(`[EngineStore:loadEpics] API returned HTTP ${response.status}`);
        }
      }
      if (epics.length > 0) {
        set({ epics, currentProjectPath: projectPath, loadEpicsLoading: false });
        console.log(`[EngineStore:loadEpics] ✓ Loaded ${epics.length} epics, set currentProjectPath`);
      } else {
        set({ epics: [], loadEpicsLoading: false });
        console.warn(`[EngineStore:loadEpics] ✗ No epics found for ${projectPath} (will retry on next trigger)`);
      }
    } catch (error) {
      console.error("[EngineStore:loadEpics] Failed:", error);
      set({ loadEpicsLoading: false });
    }
  },
  // Select an epic
  selectEpic: (epicId) => {
    set({ selectedEpic: epicId });
    if (epicId && !get().epicTaskLists[epicId]) {
      get().loadEpicTasks(epicId);
    }
  },
  // Load tasks for a specific epic
  loadEpicTasks: async (epicId) => {
    const { currentProjectPath, apiUrl } = get();
    if (!currentProjectPath) return;
    try {
      if (window.electronAPI?.engine?.getEpicTasks) {
        const result = await window.electronAPI.engine.getEpicTasks(epicId, currentProjectPath);
        if (result.tasks) {
          set((state) => ({
            epicTaskLists: {
              ...state.epicTaskLists,
              [epicId]: result
            }
          }));
          return;
        }
      }
      const response = await fetch(
        `${apiUrl}/api/v1/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(currentProjectPath)}`
      );
      if (response.ok) {
        const data = await response.json();
        set((state) => ({
          epicTaskLists: {
            ...state.epicTaskLists,
            [epicId]: data
          }
        }));
      }
    } catch (error) {
      console.error(`Failed to load tasks for ${epicId}:`, error);
    }
  },
  // Run an epic
  runEpic: async (epicId) => {
    const { currentProjectPath, apiUrl } = get();
    if (!currentProjectPath) return;
    get().updateEpicStatus(epicId, "running", 0);
    try {
      if (window.electronAPI?.engine?.runEpic) {
        await window.electronAPI.engine.runEpic(epicId, currentProjectPath);
        return;
      }
      await fetch(`${apiUrl}/api/v1/dashboard/epic/${epicId}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_path: currentProjectPath })
      });
    } catch (error) {
      console.error(`Failed to run ${epicId}:`, error);
      get().updateEpicStatus(epicId, "failed", 0);
    }
  },
  // Rerun an epic (reset all tasks and run again)
  rerunEpic: async (epicId) => {
    const { currentProjectPath, apiUrl } = get();
    if (!currentProjectPath) return;
    get().updateEpicStatus(epicId, "running", 0);
    set((state) => {
      const taskList = state.epicTaskLists[epicId];
      if (taskList) {
        const resetTasks = taskList.tasks.map((t2) => ({
          ...t2,
          status: "pending",
          actual_minutes: null,
          error_message: null
        }));
        return {
          epicTaskLists: {
            ...state.epicTaskLists,
            [epicId]: {
              ...taskList,
              tasks: resetTasks,
              completed_tasks: 0,
              failed_tasks: 0,
              progress_percent: 0,
              run_count: taskList.run_count + 1,
              last_run_at: (/* @__PURE__ */ new Date()).toISOString()
            }
          }
        };
      }
      return state;
    });
    try {
      if (window.electronAPI?.engine?.rerunEpic) {
        await window.electronAPI.engine.rerunEpic(epicId, currentProjectPath);
        return;
      }
      await fetch(`${apiUrl}/api/v1/dashboard/epic/${epicId}/rerun`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_path: currentProjectPath })
      });
    } catch (error) {
      console.error(`Failed to rerun ${epicId}:`, error);
      get().updateEpicStatus(epicId, "failed", 0);
    }
  },
  // Generate all task lists
  generateAllTaskLists: async () => {
    const { epics, currentProjectPath, apiUrl } = get();
    if (!currentProjectPath) return;
    set({ loadEpicsLoading: true });
    try {
      if (window.electronAPI?.engine?.generateTaskLists) {
        await window.electronAPI.engine.generateTaskLists(currentProjectPath);
        await get().loadEpics(currentProjectPath);
        return;
      }
      await fetch(`${apiUrl}/api/v1/dashboard/generate-task-lists`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_path: currentProjectPath })
      });
      await get().loadEpics(currentProjectPath);
    } catch (error) {
      console.error("Failed to generate task lists:", error);
    } finally {
      set({ loadEpicsLoading: false });
    }
  },
  // Update epic status (called from WebSocket events)
  updateEpicStatus: (epicId, status, progress) => {
    set((state) => ({
      epics: state.epics.map(
        (e) => e.id === epicId ? {
          ...e,
          status,
          progress_percent: progress !== void 0 ? progress : e.progress_percent,
          last_run_at: status === "running" ? (/* @__PURE__ */ new Date()).toISOString() : e.last_run_at,
          run_count: status === "running" ? e.run_count + 1 : e.run_count
        } : e
      )
    }));
  },
  // Rerun a single task (with optional fix instructions)
  rerunTask: async (epicId, taskId, fixInstructions) => {
    const { currentProjectPath } = get();
    if (!currentProjectPath) return;
    get().updateEpicTaskStatus(epicId, taskId, "running");
    try {
      if (window.electronAPI?.engine?.rerunTask) {
        const result = await window.electronAPI.engine.rerunTask(
          epicId,
          taskId,
          currentProjectPath,
          fixInstructions
        );
        if (!result.success) {
          get().updateEpicTaskStatus(epicId, taskId, "failed", result.error);
          get().addToast({
            type: "error",
            title: "Rerun Failed",
            message: result.error || "Failed to rerun task",
            taskId,
            epicId
          });
        }
        return;
      }
      const { apiUrl } = get();
      const response = await fetch(
        `${apiUrl}/api/v1/dashboard/epic/${epicId}/task/${taskId}/rerun`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_path: currentProjectPath,
            fix_instructions: fixInstructions || null
          })
        }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Rerun request failed");
      }
    } catch (error) {
      console.error(`Failed to rerun task ${taskId}:`, error);
      get().updateEpicTaskStatus(epicId, taskId, "failed", error.message);
      get().addToast({
        type: "error",
        title: "Rerun Failed",
        message: error.message || "Failed to rerun task",
        taskId,
        epicId
      });
    }
  },
  // Update epic task status (called from WebSocket events)
  updateEpicTaskStatus: (epicId, taskId, status, error) => {
    set((state) => {
      const taskList = state.epicTaskLists[epicId];
      if (!taskList) return state;
      const updatedTasks = taskList.tasks.map(
        (t2) => t2.id === taskId ? { ...t2, status, error_message: error || null } : t2
      );
      const completed = updatedTasks.filter((t2) => t2.status === "completed").length;
      const failed = updatedTasks.filter((t2) => t2.status === "failed").length;
      const total = updatedTasks.length;
      return {
        epicTaskLists: {
          ...state.epicTaskLists,
          [epicId]: {
            ...taskList,
            tasks: updatedTasks,
            completed_tasks: completed,
            failed_tasks: failed,
            progress_percent: total > 0 ? completed / total * 100 : 0
          }
        },
        // Also update epic progress
        epics: state.epics.map(
          (e) => e.id === epicId ? {
            ...e,
            progress_percent: total > 0 ? completed / total * 100 : 0,
            status: completed === total ? "completed" : failed > 0 && completed + failed === total ? "failed" : e.status
          } : e
        )
      };
    });
  },
  // Add a toast notification (max 3, auto-dismiss after 8s)
  addToast: (toast) => {
    const id2 = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const newToast = { ...toast, id: id2, timestamp: Date.now() };
    set((state) => ({
      toasts: [...state.toasts.slice(-2), newToast]
    }));
    setTimeout(() => {
      get().removeToast(id2);
    }, 8e3);
  },
  // Remove a toast by id
  removeToast: (id2) => {
    set((state) => ({
      toasts: state.toasts.filter((t2) => t2.id !== id2)
    }));
  }
}));
const engineStore = /* @__PURE__ */ Object.freeze(/* @__PURE__ */ Object.defineProperty({
  __proto__: null,
  useEngineStore
}, Symbol.toStringTag, { value: "Module" }));
function REProjectDetailView() {
  const {
    selectedREProject,
    selectREProject,
    generateFromREProject,
    stopGeneration,
    resumeWithFeedback,
    projects
  } = useProjectStore();
  const {
    generationProgress,
    generationPhase,
    taskProgress,
    agentActivity
  } = useEngineStore();
  const [activeTab, setActiveTab] = reactExports.useState("overview");
  const [expandedFeatures, setExpandedFeatures] = reactExports.useState(/* @__PURE__ */ new Set());
  const [actionPending, setActionPending] = reactExports.useState(false);
  const [elapsed, setElapsed] = reactExports.useState(0);
  if (!selectedREProject) return null;
  const project = selectedREProject;
  const projectId = `re-${project.project_id}`;
  const liveProject = projects.find((p2) => p2.id === projectId);
  const status = liveProject?.status || "idle";
  const isGenerating = status === "generating";
  const isPaused = status === "paused";
  const isStopped = status === "stopped";
  const isError = status === "error";
  const totalIssues = project.quality_issues.critical + project.quality_issues.high + project.quality_issues.medium;
  reactExports.useEffect(() => {
    if (!isGenerating) {
      setElapsed(0);
      return;
    }
    const start = Date.now();
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1e3)), 1e3);
    return () => clearInterval(interval);
  }, [isGenerating]);
  const formatElapsed = (secs) => {
    const m2 = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m2}m ${s.toString().padStart(2, "0")}s`;
  };
  const toggleFeature = (featureId) => {
    setExpandedFeatures((prev) => {
      const next = new Set(prev);
      if (next.has(featureId)) next.delete(featureId);
      else next.add(featureId);
      return next;
    });
  };
  const handleGenerate = async () => {
    setActionPending(true);
    try {
      await generateFromREProject(project.project_path);
    } finally {
      setActionPending(false);
    }
  };
  const handleStop = async () => {
    setActionPending(true);
    try {
      await stopGeneration(projectId);
    } finally {
      setActionPending(false);
    }
  };
  const handleResume = async () => {
    setActionPending(true);
    try {
      await resumeWithFeedback(projectId);
    } finally {
      setActionPending(false);
    }
  };
  const buttonConfig = (() => {
    if (actionPending) return { label: "Please wait...", icon: Loader2, color: "bg-gray-600", action: () => {
    }, disabled: true, spin: true };
    if (isGenerating) return { label: "Stop Generation", icon: Square, color: "bg-red-600 hover:bg-red-500", action: handleStop, disabled: false, spin: false };
    if (isPaused) return { label: "Resume Generation", icon: Play, color: "bg-green-600 hover:bg-green-500", action: handleResume, disabled: false, spin: false };
    if (isStopped) return { label: "Resume from Checkpoint", icon: RotateCcw, color: "bg-orange-600 hover:bg-orange-500", action: handleGenerate, disabled: false, spin: false };
    if (isError) return { label: "Retry Generation", icon: RotateCcw, color: "bg-yellow-600 hover:bg-yellow-500", action: handleGenerate, disabled: false, spin: false };
    return { label: "Generate Code", icon: Play, color: "bg-blue-600 hover:bg-blue-500", action: handleGenerate, disabled: false, spin: false };
  })();
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-gray-900", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "border-b border-gray-700 p-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 mb-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: () => selectREProject(null),
            className: "p-1 hover:bg-gray-700 rounded transition-colors",
            title: "Back to projects",
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(ArrowLeft, { className: "w-4 h-4 text-gray-400" })
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-semibold text-white", children: project.project_name }),
        project.architecture_pattern && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded", children: project.architecture_pattern }),
        isGenerating && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded animate-pulse", children: [
          "Generating ",
          generationProgress,
          "%"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1 mb-3 ml-8", children: project.tech_stack_tags.map((tag) => /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-gray-700 text-gray-300 rounded", children: tag }, tag)) }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4 ml-8 text-sm text-gray-400", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-4 h-4" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            project.requirements_count,
            " requirements"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(ListTodo, { className: "w-4 h-4" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            project.tasks_count,
            " tasks"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-4 h-4" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            project.diagram_count,
            " diagrams"
          ] })
        ] }),
        totalIssues > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: `w-4 h-4 ${project.quality_issues.critical > 0 ? "text-red-400" : "text-yellow-400"}` }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            totalIssues,
            " issues"
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2 mt-3 ml-8", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: buttonConfig.action,
            disabled: buttonConfig.disabled,
            className: `flex items-center gap-2 px-4 py-2 rounded text-sm font-medium text-white transition-colors ${buttonConfig.color} ${buttonConfig.disabled ? "opacity-50 cursor-wait" : ""}`,
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(buttonConfig.icon, { className: `w-4 h-4 ${buttonConfig.spin ? "animate-spin" : ""}` }),
              buttonConfig.label
            ]
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => window.electronAPI?.fs?.showInExplorer(project.project_path),
            className: "flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium text-gray-300 transition-colors",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(FolderOpen, { className: "w-4 h-4" }),
              "Open in Explorer"
            ]
          }
        )
      ] }),
      (isGenerating || isPaused) && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-4 ml-8 bg-gray-800 rounded-lg p-4 border border-gray-700", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between mb-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm font-medium text-gray-300", children: isPaused ? "Generation Paused" : generationPhase || "Starting..." }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-sm text-gray-400", children: [
            generationProgress,
            "%"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-full bg-gray-700 rounded-full h-2 mb-3", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
          "div",
          {
            className: `h-2 rounded-full transition-all duration-500 ${isPaused ? "bg-yellow-500" : "bg-blue-500"}`,
            style: { width: `${Math.max(1, generationProgress)}%` }
          }
        ) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-4 gap-3 mb-3 text-xs", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle2, { className: "w-3.5 h-3.5 text-green-400" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400", children: "Completed:" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-green-300 font-medium", children: taskProgress.completed })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 text-blue-400 animate-spin" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400", children: "Running:" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-blue-300 font-medium", children: taskProgress.running })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-3.5 h-3.5 text-red-400" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400", children: "Failed:" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-300 font-medium", children: taskProgress.failed })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-3.5 h-3.5 text-gray-400" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400", children: "Elapsed:" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 font-medium", children: formatElapsed(elapsed) })
          ] })
        ] }),
        agentActivity.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "border-t border-gray-700 pt-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500 mb-1 block", children: "Latest Activity" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-0.5 max-h-20 overflow-auto", children: agentActivity.slice(-5).reverse().map((item, i) => /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-xs flex items-center gap-1.5", children: typeof item === "string" ? /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400 truncate", children: item }) : /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: item.status === "completed" ? "text-green-400" : item.status === "failed" ? "text-red-400" : "text-blue-400", children: item.status === "completed" ? "✅" : item.status === "failed" ? "❌" : "⏳" }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-gray-400 truncate", children: [
              item.agent,
              ": ",
              item.action
            ] })
          ] }) }, i)) })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "border-b border-gray-700 flex", children: ["overview", "tasks", "quality"].map((tab) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: () => setActiveTab(tab),
        className: `px-4 py-2 text-sm font-medium capitalize transition-colors ${activeTab === tab ? "text-blue-400 border-b-2 border-blue-400" : "text-gray-400 hover:text-gray-200"}`,
        children: [
          tab,
          tab === "quality" && totalIssues > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "ml-1.5 text-xs px-1.5 py-0.5 bg-yellow-500/20 text-yellow-300 rounded", children: totalIssues })
        ]
      },
      tab
    )) }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto p-4", children: [
      activeTab === "overview" && /* @__PURE__ */ jsxRuntimeExports.jsx(OverviewTab$1, { project }),
      activeTab === "tasks" && /* @__PURE__ */ jsxRuntimeExports.jsx(TasksTab, { project, expandedFeatures, toggleFeature }),
      activeTab === "quality" && /* @__PURE__ */ jsxRuntimeExports.jsx(QualityTab, { project })
    ] })
  ] });
}
function OverviewTab$1({ project }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-6", children: [
    project.master_document_excerpt && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-sm font-medium text-gray-300 mb-2", children: "Master Document" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "bg-gray-800 rounded p-3 text-sm text-gray-400 whitespace-pre-wrap max-h-64 overflow-auto", children: project.master_document_excerpt })
    ] }),
    Object.keys(project.tech_stack_full).length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-sm font-medium text-gray-300 mb-2", children: "Tech Stack" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "bg-gray-800 rounded p-3", children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-2 gap-2 text-sm", children: Object.entries(project.tech_stack_full).filter(([, val]) => val && val !== "none" && val !== "").map(([key, val]) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: key.replace(/_/g, " ") }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300", children: val })
      ] }, key)) }) })
    ] }),
    project.feature_breakdown.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("h3", { className: "text-sm font-medium text-gray-300 mb-2", children: [
        "Features (",
        project.feature_breakdown.length,
        ")"
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-1", children: project.feature_breakdown.map((feat) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-gray-800 rounded px-3 py-2 flex items-center justify-between text-sm", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300", children: feat.feature_name || feat.feature_id }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
          feat.requirements.length,
          " reqs"
        ] })
      ] }, feat.feature_id)) })
    ] })
  ] });
}
function TasksTab({
  project,
  expandedFeatures,
  toggleFeature
}) {
  const featureEntries = Object.entries(project.tasks_by_feature);
  if (featureEntries.length === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-500 text-sm", children: "No tasks found." });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2", children: featureEntries.map(([featureId, tasks]) => {
    const isExpanded = expandedFeatures.has(featureId);
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-gray-800 rounded", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => toggleFeature(featureId),
          className: "w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-gray-750 transition-colors",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
              isExpanded ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-4 h-4 text-gray-400" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-4 h-4 text-gray-400" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium text-gray-300", children: featureId })
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
              tasks.length,
              " tasks"
            ] })
          ]
        }
      ),
      isExpanded && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "px-3 pb-2 space-y-1", children: tasks.map((task) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between px-3 py-1.5 bg-gray-900/50 rounded text-xs", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 min-w-0", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500 shrink-0", children: task.id }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 truncate", children: task.title })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 shrink-0 ml-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `px-1.5 py-0.5 rounded ${task.complexity === "complex" ? "bg-red-500/20 text-red-300" : task.complexity === "medium" ? "bg-yellow-500/20 text-yellow-300" : "bg-green-500/20 text-green-300"}`, children: task.complexity }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-gray-500", children: [
            task.estimated_hours,
            "h"
          ] })
        ] })
      ] }, task.id)) })
    ] }, featureId);
  }) });
}
function QualityTab({ project }) {
  if (project.quality_issues_list.length === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-green-400 text-sm", children: "No quality issues found." });
  }
  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  const sorted = [...project.quality_issues_list].sort(
    (a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3)
  );
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-2", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-3 mb-4 text-sm", children: [
      project.quality_issues.critical > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "px-2 py-1 bg-red-500/20 text-red-300 rounded", children: [
        project.quality_issues.critical,
        " critical"
      ] }),
      project.quality_issues.high > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "px-2 py-1 bg-orange-500/20 text-orange-300 rounded", children: [
        project.quality_issues.high,
        " high"
      ] }),
      project.quality_issues.medium > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "px-2 py-1 bg-yellow-500/20 text-yellow-300 rounded", children: [
        project.quality_issues.medium,
        " medium"
      ] })
    ] }),
    sorted.map((issue) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-gray-800 rounded px-3 py-2 flex items-start gap-3 text-sm", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: `w-4 h-4 shrink-0 mt-0.5 ${issue.severity === "critical" ? "text-red-400" : issue.severity === "high" ? "text-orange-400" : "text-yellow-400"}` }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "min-w-0", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 font-medium", children: issue.title }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: issue.category })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: issue.id })
      ] })
    ] }, issue.id))
  ] });
}
function REProjectCard({ project, onSelect, onGenerate }) {
  const [generating, setGenerating] = reactExports.useState(false);
  const totalIssues = project.quality_issues.critical + project.quality_issues.high + project.quality_issues.medium;
  const handleGenerate = async (e) => {
    e.stopPropagation();
    setGenerating(true);
    try {
      await onGenerate(project.project_path);
    } finally {
      setGenerating(false);
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: "bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-blue-500/50 transition-colors cursor-pointer",
      onClick: () => onSelect(project.project_path),
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start justify-between mb-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 min-w-0", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Folder, { className: "w-5 h-5 text-blue-400 shrink-0" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "font-medium text-white truncate", children: project.project_name })
          ] }),
          project.architecture_pattern && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded shrink-0 ml-2", children: project.architecture_pattern })
        ] }),
        project.tech_stack_tags.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1 mb-3", children: project.tech_stack_tags.map((tag) => /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded", children: tag }, tag)) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-4 gap-2 mb-3 text-xs text-gray-400", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", title: "Requirements", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-3 h-3" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: project.requirements_count })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", title: "Tasks", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(ListTodo, { className: "w-3 h-3" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: project.tasks_count })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", title: "Diagrams", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-3 h-3" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: project.diagram_count })
          ] }),
          totalIssues > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", title: `Quality Issues: ${project.quality_issues.critical} critical, ${project.quality_issues.high} high`, children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: `w-3 h-3 ${project.quality_issues.critical > 0 ? "text-red-400" : "text-yellow-400"}` }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: totalIssues })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 mb-3", children: [
          project.has_api_spec && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-1.5 py-0.5 bg-green-500/20 text-green-300 rounded", children: "API Spec" }),
          project.has_master_document && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-1.5 py-0.5 bg-blue-500/20 text-blue-300 rounded", children: "Master Doc" })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: handleGenerate,
            disabled: generating,
            className: `w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded text-sm font-medium text-white transition-colors ${generating ? "bg-blue-600/50 cursor-wait" : "bg-blue-600 hover:bg-blue-500"}`,
            children: generating ? /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 animate-spin" }),
              "Starting Generation..."
            ] }) : /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Play, { className: "w-3.5 h-3.5" }),
              "Generate Code"
            ] })
          }
        )
      ]
    }
  );
}
function ProjectSpace() {
  const {
    activeProjectId,
    getProject,
    startGeneration,
    stopProject,
    selectedREProject,
    reProjects,
    selectREProject,
    generateFromREProject
  } = useProjectStore();
  const activeProject = activeProjectId ? getProject(activeProjectId) : null;
  if (selectedREProject) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx(REProjectDetailView, {});
  }
  if (activeProject && (activeProject.status === "generating" || activeProject.status === "running")) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full p-6 overflow-auto", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
      ProjectCard,
      {
        project: activeProject,
        onStartGeneration: () => startGeneration(activeProject.id, true),
        onStartPreview: () => startGeneration(activeProject.id, false),
        onStopPreview: () => stopProject(activeProject.id)
      }
    ) });
  }
  if (activeProject) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full p-6 overflow-auto", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
      ProjectCard,
      {
        project: activeProject,
        onStartGeneration: () => startGeneration(activeProject.id, true),
        onStartPreview: () => startGeneration(activeProject.id, false),
        onStopPreview: () => stopProject(activeProject.id)
      }
    ) });
  }
  if (reProjects.length > 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full p-6 overflow-auto", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between mb-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-semibold text-white", children: "Local RE Projects" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs px-2 py-1 bg-gray-700 text-gray-400 rounded", children: [
          reProjects.length,
          " projects"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4", children: reProjects.map((project) => /* @__PURE__ */ jsxRuntimeExports.jsx(
        REProjectCard,
        {
          project,
          onSelect: selectREProject,
          onGenerate: generateFromREProject
        },
        project.project_id
      )) })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsx(OrchestratorProjectsPanel, {});
}
const API_BASE_URL = "http://localhost:8000";
const getApiBase = () => {
  return API_BASE_URL;
};
async function fetchPendingClarifications() {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch clarifications: ${response.statusText}`);
  }
  return response.json();
}
async function submitClarificationChoice(clarificationId, interpretationId) {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications/${clarificationId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interpretation_id: interpretationId })
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Failed to submit choice");
  }
  return response.json();
}
async function useAllDefaultClarifications() {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications/resolve-all-defaults`,
    { method: "POST" }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Failed to use defaults");
  }
  return response.json();
}
function formatTimeRemaining(timeoutAt) {
  if (!timeoutAt) return "";
  const now = /* @__PURE__ */ new Date();
  const timeout = new Date(timeoutAt);
  const diffMs = timeout.getTime() - now.getTime();
  if (diffMs <= 0) return "expired";
  const diffSeconds = Math.floor(diffMs / 1e3);
  const minutes = Math.floor(diffSeconds / 60);
  const seconds = diffSeconds % 60;
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}
function getPriorityLabel(priority) {
  switch (priority) {
    case 1:
      return "High";
    case 2:
      return "Medium";
    case 3:
      return "Low";
    default:
      return "Unknown";
  }
}
function getSeverityColorClass(severity) {
  switch (severity) {
    case "high":
      return "border-red-500 bg-red-500/10";
    case "medium":
      return "border-amber-500 bg-amber-500/10";
    case "low":
      return "border-blue-500 bg-blue-500/10";
    default:
      return "border-zinc-500 bg-zinc-500/10";
  }
}
const useClarificationStore = create((set, get) => ({
  // Initial state
  pending: [],
  statistics: null,
  queueMode: false,
  isPanelOpen: false,
  selectedId: null,
  isEditorOpen: false,
  isLoading: false,
  error: null,
  lastUpdated: null,
  // Simple setters
  setPending: (items) => set({ pending: items }),
  setStatistics: (stats) => set({ statistics: stats }),
  // Panel actions
  openPanel: () => set({ isPanelOpen: true }),
  closePanel: () => set({ isPanelOpen: false }),
  // Editor actions
  selectClarification: (id2) => set({
    selectedId: id2,
    isEditorOpen: true,
    isPanelOpen: false
  }),
  closeEditor: () => set({
    isEditorOpen: false,
    selectedId: null
  }),
  clearError: () => set({ error: null }),
  // Async actions
  refreshPending: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await fetchPendingClarifications();
      set({
        pending: response.pending,
        statistics: response.statistics,
        queueMode: response.queue_mode,
        isLoading: false,
        lastUpdated: /* @__PURE__ */ new Date()
      });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to fetch clarifications"
      });
    }
  },
  submitChoice: async (clarificationId, interpretationId) => {
    set({ isLoading: true, error: null });
    try {
      const response = await submitClarificationChoice(clarificationId, interpretationId);
      if (response.success) {
        await get().refreshPending();
        set({
          isEditorOpen: false,
          selectedId: null,
          isLoading: false
        });
        return true;
      } else {
        set({ isLoading: false, error: "Failed to submit choice" });
        return false;
      }
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to submit choice"
      });
      return false;
    }
  },
  useAllDefaults: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await useAllDefaultClarifications();
      if (response.success) {
        await get().refreshPending();
        set({
          isPanelOpen: false,
          isLoading: false
        });
        return true;
      } else {
        set({ isLoading: false, error: "Failed to use defaults" });
        return false;
      }
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to use defaults"
      });
      return false;
    }
  }
}));
const useSelectedClarification = () => {
  const pending = useClarificationStore((state) => state.pending);
  const selectedId = useClarificationStore((state) => state.selectedId);
  if (!selectedId) return null;
  return pending.find((c) => c.id === selectedId) || null;
};
const usePendingCount = () => {
  return useClarificationStore((state) => state.pending.length);
};
const useHighPriorityCount = () => {
  return useClarificationStore(
    (state) => state.pending.filter((c) => c.priority === 1).length
  );
};
function getEpicTaskStatusIcon(status) {
  switch (status) {
    case "completed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-3.5 h-3.5 text-green-500" });
    case "failed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-3.5 h-3.5 text-red-500" });
    case "running":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 text-yellow-500 animate-spin" });
    case "skipped":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(SkipForward, { className: "w-3.5 h-3.5 text-gray-400" });
    case "pending":
    default:
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-3.5 h-3.5 text-gray-500" });
  }
}
function getTaskTypeIcon(type) {
  switch (type) {
    case "schema":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Database, { className: "w-3 h-3" });
    case "api":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Server, { className: "w-3 h-3" });
    case "frontend":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Monitor, { className: "w-3 h-3" });
    case "test":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(TestTube, { className: "w-3 h-3" });
    case "integration":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Link2, { className: "w-3 h-3" });
    default:
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-3 h-3" });
  }
}
function getTaskTypeBadge(type) {
  const colors = {
    schema: "bg-purple-500/20 text-purple-400",
    api: "bg-blue-500/20 text-blue-400",
    frontend: "bg-cyan-500/20 text-cyan-400",
    test: "bg-green-500/20 text-green-400",
    integration: "bg-orange-500/20 text-orange-400"
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: `text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1 ${colors[type] || "bg-gray-500/20 text-gray-400"}`, children: [
    getTaskTypeIcon(type),
    type
  ] });
}
function EpicTaskListView({ taskList }) {
  const [filter, setFilter] = reactExports.useState("all");
  const [collapsedGroups, setCollapsedGroups] = reactExports.useState(/* @__PURE__ */ new Set());
  const tasks = taskList.tasks;
  const progress = reactExports.useMemo(() => {
    const total = tasks.length;
    const completed = tasks.filter((t2) => t2.status === "completed").length;
    const running = tasks.filter((t2) => t2.status === "running").length;
    const failed = tasks.filter((t2) => t2.status === "failed").length;
    const skipped = tasks.filter((t2) => t2.status === "skipped").length;
    const pending = total - completed - running - failed - skipped;
    return {
      total,
      completed,
      running,
      failed,
      skipped,
      pending,
      percent_complete: total > 0 ? completed / total * 100 : 0
    };
  }, [tasks]);
  const grouped = reactExports.useMemo(() => {
    const filtered = filter === "all" ? tasks : tasks.filter((t2) => t2.status === filter);
    const groups = {};
    for (const task of filtered) {
      const group = task.type || "other";
      if (!groups[group]) groups[group] = [];
      groups[group].push(task);
    }
    return groups;
  }, [tasks, filter]);
  const toggleGroup = (group) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };
  const filterOptions = [
    { key: "all", label: "All", count: progress.total },
    { key: "running", label: "Running", count: progress.running },
    { key: "failed", label: "Failed", count: progress.failed },
    { key: "pending", label: "Pending", count: progress.pending },
    { key: "completed", label: "Done", count: progress.completed }
  ];
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col h-full gap-2", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between text-xs text-gray-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-engine-primary font-medium", children: taskList.epic_name }),
        " — ",
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: progress.completed }),
        "/",
        progress.total,
        " completed",
        progress.running > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          ", ",
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-yellow-400", children: [
            progress.running,
            " running"
          ] })
        ] }),
        progress.failed > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          ", ",
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-red-400", children: [
            progress.failed,
            " failed"
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "font-mono", children: [
        progress.percent_complete.toFixed(0),
        "%"
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-2 bg-gray-700 rounded-full overflow-hidden flex", children: progress.total > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "bg-green-500 transition-all duration-300",
          style: { width: `${progress.completed / progress.total * 100}%` }
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "bg-yellow-500 transition-all duration-300",
          style: { width: `${progress.running / progress.total * 100}%` }
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "bg-red-500 transition-all duration-300",
          style: { width: `${progress.failed / progress.total * 100}%` }
        }
      )
    ] }) }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-1 items-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Filter, { className: "w-3 h-3 text-gray-500" }),
      filterOptions.map((opt) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => setFilter(opt.key),
          className: `text-[11px] px-2 py-0.5 rounded-full transition ${filter === opt.key ? "bg-engine-primary/20 text-engine-primary" : "bg-gray-700/50 text-gray-400 hover:text-white"}`,
          children: [
            opt.label,
            opt.count > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "ml-1 opacity-70", children: opt.count })
          ]
        },
        opt.key
      ))
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-auto space-y-1", children: Object.entries(grouped).map(([group, groupTasks]) => {
      const isCollapsed = collapsedGroups.has(group);
      const groupCompleted = groupTasks.filter((t2) => t2.status === "completed").length;
      const groupTotal = groupTasks.length;
      return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => toggleGroup(group),
            className: "flex items-center gap-1.5 w-full text-left text-xs py-1 px-1 rounded hover:bg-gray-700/30 transition",
            children: [
              isCollapsed ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-3 h-3 text-gray-500" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-3 h-3 text-gray-500" }),
              getTaskTypeIcon(group),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 font-medium capitalize", children: group }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-gray-500 ml-auto", children: [
                groupCompleted,
                "/",
                groupTotal
              ] })
            ]
          }
        ),
        !isCollapsed && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "ml-4 space-y-0.5", children: groupTasks.map((task) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "div",
          {
            className: `flex items-center gap-2 text-xs py-1 px-2 rounded ${task.status === "running" ? "bg-yellow-500/5" : task.status === "failed" ? "bg-red-500/5" : ""}`,
            children: [
              getEpicTaskStatusIcon(task.status),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 truncate flex-1", title: `${task.id}: ${task.description}`, children: task.title }),
              getTaskTypeBadge(task.type),
              task.error_message && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400 truncate max-w-[150px]", title: task.error_message, children: task.error_message })
            ]
          },
          task.id
        )) })
      ] }, group);
    }) })
  ] });
}
function getStatusIcon$2(status) {
  switch (status) {
    case "completed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-3.5 h-3.5 text-green-500" });
    case "failed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-3.5 h-3.5 text-red-500" });
    case "running":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 text-yellow-500 animate-spin" });
    case "pending":
    default:
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-3.5 h-3.5 text-gray-500" });
  }
}
function getComplexityBadge(complexity) {
  const colors = {
    simple: "bg-green-500/20 text-green-400",
    medium: "bg-yellow-500/20 text-yellow-400",
    complex: "bg-red-500/20 text-red-400"
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `text-[10px] px-1.5 py-0.5 rounded ${colors[complexity] || colors.medium}`, children: complexity });
}
function TaskList() {
  const { taskChunks, taskProgress, taskClarifications, epicTaskLists, selectedEpic, epics } = useEngineStore();
  const [filter, setFilter] = reactExports.useState("all");
  const [collapsedGroups, setCollapsedGroups] = reactExports.useState(/* @__PURE__ */ new Set());
  const epicTaskList = reactExports.useMemo(() => {
    if (taskChunks.length > 0) return null;
    const epicId = selectedEpic || epics.find((e) => epicTaskLists[e.id]?.tasks?.length > 0)?.id;
    if (!epicId || !epicTaskLists[epicId] || !epicTaskLists[epicId].tasks?.length) return null;
    return epicTaskLists[epicId];
  }, [taskChunks.length, epicTaskLists, selectedEpic, epics]);
  const chunkClarifications = reactExports.useMemo(() => {
    const map = /* @__PURE__ */ new Map();
    for (const chunk of taskChunks) {
      const related = taskClarifications.filter(
        (c) => c.requirement_id && chunk.requirements.includes(c.requirement_id)
      );
      if (related.length > 0) {
        map.set(chunk.chunk_id, related);
      }
    }
    return map;
  }, [taskChunks, taskClarifications]);
  const grouped = reactExports.useMemo(() => {
    const filtered = filter === "all" ? taskChunks : taskChunks.filter((c) => c.status === filter);
    const groups = {};
    for (const chunk of filtered) {
      const group = chunk.service_group || "ungrouped";
      if (!groups[group]) groups[group] = [];
      groups[group].push(chunk);
    }
    return groups;
  }, [taskChunks, filter]);
  const toggleGroup = (group) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };
  if (epicTaskList) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx(EpicTaskListView, { taskList: epicTaskList });
  }
  if (taskChunks.length === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full flex items-center justify-center text-gray-500", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-8 h-8 mx-auto mb-2 opacity-50" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "No tasks yet" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs mt-1", children: "Tasks appear when generation starts" })
    ] }) });
  }
  const filterOptions = [
    { key: "all", label: "All", count: taskProgress.total },
    { key: "running", label: "Running", count: taskProgress.running },
    { key: "failed", label: "Failed", count: taskProgress.failed },
    { key: "pending", label: "Pending", count: taskProgress.pending },
    { key: "completed", label: "Done", count: taskProgress.completed }
  ];
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col h-full gap-2", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between text-xs text-gray-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: taskProgress.completed }),
        "/",
        taskProgress.total,
        " completed",
        taskProgress.running > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          ", ",
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-yellow-400", children: [
            taskProgress.running,
            " running"
          ] })
        ] }),
        taskProgress.failed > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          ", ",
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-red-400", children: [
            taskProgress.failed,
            " failed"
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "font-mono", children: [
        taskProgress.percent_complete.toFixed(0),
        "%"
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-2 bg-gray-700 rounded-full overflow-hidden flex", children: taskProgress.total > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "bg-green-500 transition-all duration-300",
          style: { width: `${taskProgress.completed / taskProgress.total * 100}%` }
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "bg-yellow-500 transition-all duration-300",
          style: { width: `${taskProgress.running / taskProgress.total * 100}%` }
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "bg-red-500 transition-all duration-300",
          style: { width: `${taskProgress.failed / taskProgress.total * 100}%` }
        }
      )
    ] }) }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-1 items-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Filter, { className: "w-3 h-3 text-gray-500" }),
      filterOptions.map((opt) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => setFilter(opt.key),
          className: `text-[11px] px-2 py-0.5 rounded-full transition ${filter === opt.key ? "bg-engine-primary/20 text-engine-primary" : "bg-gray-700/50 text-gray-400 hover:text-white"}`,
          children: [
            opt.label,
            opt.count > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "ml-1 opacity-70", children: opt.count })
          ]
        },
        opt.key
      ))
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-auto space-y-1", children: Object.entries(grouped).map(([group, chunks]) => {
      const isCollapsed = collapsedGroups.has(group);
      const groupCompleted = chunks.filter((c) => c.status === "completed").length;
      const groupTotal = chunks.length;
      return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => toggleGroup(group),
            className: "flex items-center gap-1.5 w-full text-left text-xs py-1 px-1 rounded hover:bg-gray-700/30 transition",
            children: [
              isCollapsed ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-3 h-3 text-gray-500" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-3 h-3 text-gray-500" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-3 h-3 text-engine-primary" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 font-medium", children: group }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-gray-500 ml-auto", children: [
                groupCompleted,
                "/",
                groupTotal
              ] })
            ]
          }
        ),
        !isCollapsed && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "ml-4 space-y-0.5", children: chunks.map((chunk) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "div",
          {
            className: `flex items-center gap-2 text-xs py-1 px-2 rounded ${chunk.status === "running" ? "bg-yellow-500/5" : chunk.status === "failed" ? "bg-red-500/5" : ""}`,
            children: [
              getStatusIcon$2(chunk.status),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300 truncate flex-1", title: chunk.chunk_id, children: chunk.chunk_id }),
              getComplexityBadge(chunk.complexity),
              chunkClarifications.has(chunk.chunk_id) && /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: async (e) => {
                    e.stopPropagation();
                    const clars = chunkClarifications.get(chunk.chunk_id);
                    await useClarificationStore.getState().refreshPending();
                    useClarificationStore.getState().selectClarification(clars[0].id);
                  },
                  className: "text-amber-400 hover:text-amber-300 transition",
                  title: `${chunkClarifications.get(chunk.chunk_id).length} clarification(s)`,
                  children: /* @__PURE__ */ jsxRuntimeExports.jsx(HelpCircle, { className: "w-3.5 h-3.5" })
                }
              ),
              chunk.error_message && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400 truncate max-w-[120px]", title: chunk.error_message, children: chunk.error_message })
            ]
          },
          chunk.chunk_id
        )) })
      ] }, group);
    }) })
  ] });
}
function getStatusIcon$1(status, size = "w-4 h-4") {
  switch (status) {
    case "completed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: `${size} text-green-500` });
    case "failed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: `${size} text-red-500` });
    case "running":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: `${size} text-yellow-500 animate-spin` });
    case "pending":
    default:
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: `${size} text-gray-500` });
  }
}
function getEpicNumber(epicId) {
  return epicId.replace("EPIC-", "").replace(/^0+/, "") || "0";
}
function EpicSelector({ onRunEpic, onRerunEpic, onGenerateTaskList }) {
  const { epics, selectedEpic, epicTaskLists, selectEpic, loadEpicsLoading } = useEngineStore();
  const [showDetails, setShowDetails] = reactExports.useState(false);
  const currentEpic = reactExports.useMemo(() => {
    return epics.find((e) => e.id === selectedEpic);
  }, [epics, selectedEpic]);
  const currentTaskList = reactExports.useMemo(() => {
    return selectedEpic ? epicTaskLists[selectedEpic] : null;
  }, [selectedEpic, epicTaskLists]);
  const stats = reactExports.useMemo(() => {
    const total = epics.length;
    const completed = epics.filter((e) => e.status === "completed").length;
    const running = epics.filter((e) => e.status === "running").length;
    const failed = epics.filter((e) => e.status === "failed").length;
    const pending = epics.filter((e) => e.status === "pending").length;
    return { total, completed, running, failed, pending };
  }, [epics]);
  if (epics.length === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex items-center justify-between", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("h3", { className: "text-sm font-medium text-gray-300 flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-4 h-4 text-engine-primary" }),
        "Epics"
      ] }) }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center py-6 text-gray-500", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(ListChecks, { className: "w-8 h-8 mx-auto mb-2 opacity-50" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm", children: "No epics loaded" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs mt-1", children: "Select a project to load epics" }),
        onGenerateTaskList && /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: onGenerateTaskList,
            disabled: loadEpicsLoading,
            className: "mt-3 px-4 py-2 bg-engine-primary hover:bg-engine-primary/90 disabled:bg-gray-600 text-white rounded text-sm flex items-center gap-2 mx-auto transition",
            children: [
              loadEpicsLoading ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Zap, { className: "w-4 h-4" }),
              "Generate Task List"
            ]
          }
        )
      ] })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-3", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("h3", { className: "text-sm font-medium text-gray-300 flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-4 h-4 text-engine-primary" }),
        "Epics (",
        stats.total,
        ")"
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 text-[11px]", children: [
        stats.completed > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-green-400", children: [
          stats.completed,
          " done"
        ] }),
        stats.running > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-yellow-400 ml-1", children: [
          stats.running,
          " running"
        ] }),
        stats.failed > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-red-400 ml-1", children: [
          stats.failed,
          " failed"
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-5 gap-1.5", children: epics.map((epic) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: () => selectEpic(epic.id),
        className: `relative p-2 rounded border transition-all ${selectedEpic === epic.id ? "border-engine-primary bg-engine-primary/10 ring-1 ring-engine-primary/50" : "border-gray-700 hover:border-gray-600 bg-gray-800/50"}`,
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
              getStatusIcon$1(epic.status, "w-3 h-3"),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs font-mono font-medium text-white", children: getEpicNumber(epic.id) })
            ] }),
            epic.run_count > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[9px] text-gray-500", children: [
              "#",
              epic.run_count
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-1 bg-gray-700 rounded-full mt-1.5 overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: `h-full transition-all duration-300 ${epic.status === "failed" ? "bg-red-500" : epic.status === "completed" ? "bg-green-500" : epic.status === "running" ? "bg-yellow-500" : "bg-gray-600"}`,
              style: { width: `${epic.progress_percent}%` }
            }
          ) }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute inset-0 opacity-0 hover:opacity-100 transition-opacity", children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-gray-900 border border-gray-700 rounded text-[10px] text-white whitespace-nowrap z-10 pointer-events-none", children: epic.name }) })
        ]
      },
      epic.id
    )) }),
    currentEpic && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "border border-gray-700 rounded-lg bg-gray-800/30 overflow-hidden", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between p-2 border-b border-gray-700/50", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
          getStatusIcon$1(currentEpic.status),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm font-medium text-white", children: currentEpic.id }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400 mx-1", children: "-" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-300", children: currentEpic.name })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: () => setShowDetails(!showDetails),
            className: "text-gray-400 hover:text-white transition",
            children: showDetails ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-4 h-4" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-4 h-4" })
          }
        )
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4 px-3 py-2 text-xs text-gray-400", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: currentEpic.user_stories.length }),
          " User Stories"
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: currentEpic.entities.length }),
          " Entities"
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: currentEpic.requirements.length }),
          " Requirements"
        ] }),
        currentTaskList && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "ml-auto", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: currentTaskList.total_tasks }),
          " Tasks",
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-gray-500 ml-1", children: [
            "(~",
            currentTaskList.estimated_total_minutes,
            " min)"
          ] })
        ] })
      ] }),
      currentTaskList && currentTaskList.total_tasks > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-3 pb-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-[11px] text-gray-400 mb-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            currentTaskList.completed_tasks,
            "/",
            currentTaskList.total_tasks,
            " tasks"
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "ml-auto font-mono", children: [
            currentTaskList.progress_percent.toFixed(0),
            "%"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-1.5 bg-gray-700 rounded-full overflow-hidden flex", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: "bg-green-500 transition-all duration-300",
              style: { width: `${currentTaskList.completed_tasks / currentTaskList.total_tasks * 100}%` }
            }
          ),
          currentTaskList.failed_tasks > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: "bg-red-500 transition-all duration-300",
              style: { width: `${currentTaskList.failed_tasks / currentTaskList.total_tasks * 100}%` }
            }
          )
        ] })
      ] }),
      showDetails && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-3 py-2 border-t border-gray-700/50 text-xs text-gray-400 space-y-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: currentEpic.description }),
        currentEpic.last_run_at && /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-gray-500", children: [
          "Last run: ",
          new Date(currentEpic.last_run_at).toLocaleString()
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2 p-2 border-t border-gray-700/50", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => onRunEpic?.(currentEpic.id),
            disabled: currentEpic.status === "running",
            className: `flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition ${currentEpic.status === "running" ? "bg-gray-700 text-gray-500 cursor-not-allowed" : "bg-engine-primary hover:bg-engine-primary/90 text-white"}`,
            children: [
              currentEpic.status === "running" ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 animate-spin" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Play, { className: "w-3.5 h-3.5" }),
              currentEpic.status === "running" ? "Running..." : "Run"
            ]
          }
        ),
        (currentEpic.status === "completed" || currentEpic.status === "failed") && /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => onRerunEpic?.(currentEpic.id),
            className: "flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs font-medium transition",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(RotateCcw, { className: "w-3.5 h-3.5" }),
              "Rerun"
            ]
          }
        )
      ] })
    ] }),
    epics.length > 0 && onGenerateTaskList && !Object.keys(epicTaskLists).length && /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: onGenerateTaskList,
        disabled: loadEpicsLoading,
        className: "w-full px-4 py-2 bg-engine-primary/20 hover:bg-engine-primary/30 border border-engine-primary/50 text-engine-primary rounded text-sm flex items-center justify-center gap-2 transition",
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Zap, { className: "w-4 h-4" }),
          "Generate All Task Lists"
        ]
      }
    )
  ] });
}
const ROLE_META = {
  primary: { label: "Primary (SDK)", icon: "🔵", color: "text-blue-400" },
  cli: { label: "CLI", icon: "⚡", color: "text-yellow-400" },
  mcp_standard: { label: "MCP Standard", icon: "🟢", color: "text-green-400" },
  mcp_agent: { label: "MCP Agent", icon: "🤖", color: "text-purple-400" },
  judge: { label: "Judge", icon: "⚖️", color: "text-orange-400" },
  reasoning: { label: "Reasoning", icon: "🧠", color: "text-pink-400" },
  enrichment: { label: "Enrichment", icon: "📚", color: "text-cyan-400" }
};
const API_BASE$2 = "http://localhost:8000";
const useLLMConfigStore = create((set, get) => ({
  config: null,
  isLoading: false,
  isSaving: false,
  error: null,
  lastSaved: null,
  validation: null,
  editedModels: {},
  isDirty: false,
  fetchConfig: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await fetch(`${API_BASE$2}/api/v1/llm-config`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      set({
        config: data,
        editedModels: { ...data.models },
        isLoading: false,
        isDirty: false,
        validation: null
      });
    } catch (error) {
      set({ isLoading: false, error: String(error) });
    }
  },
  updateRole: (role, field, value) => {
    const { editedModels, config } = get();
    const current = editedModels[role];
    if (!current) return;
    const updated = { ...current, [field]: value };
    const newEdited = { ...editedModels, [role]: updated };
    const original = config?.models || {};
    let dirty = false;
    for (const r2 of Object.keys(newEdited)) {
      const orig = original[r2];
      const edit = newEdited[r2];
      if (!orig || orig.model !== edit.model || orig.provider !== edit.provider || orig.max_tokens !== edit.max_tokens) {
        dirty = true;
        break;
      }
    }
    set({ editedModels: newEdited, isDirty: dirty, validation: null });
  },
  saveConfig: async () => {
    const { editedModels } = get();
    set({ isSaving: true, error: null });
    try {
      const response = await fetch(`${API_BASE$2}/api/v1/llm-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ models: editedModels })
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
        const detail = errData.detail;
        if (typeof detail === "object" && detail.errors) {
          set({
            isSaving: false,
            validation: { valid: false, errors: detail.errors, warnings: detail.warnings || [] }
          });
          return false;
        }
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      const updatedConfig = await response.json();
      set({
        config: updatedConfig,
        editedModels: { ...updatedConfig.models },
        isSaving: false,
        isDirty: false,
        lastSaved: (/* @__PURE__ */ new Date()).toISOString(),
        validation: { valid: true, errors: [], warnings: [] }
      });
      return true;
    } catch (error) {
      set({ isSaving: false, error: String(error) });
      return false;
    }
  },
  validateConfig: async () => {
    const { editedModels } = get();
    try {
      const response = await fetch(`${API_BASE$2}/api/v1/llm-config/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ models: editedModels })
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const result = await response.json();
      set({ validation: result });
      return result;
    } catch (error) {
      const result = { valid: false, errors: [String(error)], warnings: [] };
      set({ validation: result });
      return result;
    }
  },
  resetChanges: () => {
    const { config } = get();
    if (config) {
      set({
        editedModels: { ...config.models },
        isDirty: false,
        validation: null,
        error: null
      });
    }
  },
  reloadConfig: async () => {
    try {
      await fetch(`${API_BASE$2}/api/v1/llm-config/reload`, { method: "POST" });
      await get().fetchConfig();
    } catch (error) {
      set({ error: String(error) });
    }
  }
}));
const PROVIDER_OPTIONS = [
  { value: "anthropic", label: "Anthropic (Direct SDK)" },
  { value: "openrouter", label: "OpenRouter" }
];
const TOKEN_PRESETS = [2048, 4096, 8192, 16384, 32768, 65536, 131072];
function LLMConfigEditor() {
  const {
    config,
    isLoading,
    isSaving,
    error,
    lastSaved,
    validation,
    editedModels,
    isDirty,
    fetchConfig,
    updateRole,
    saveConfig,
    validateConfig,
    resetChanges,
    reloadConfig
  } = useLLMConfigStore();
  const [expandedRole, setExpandedRole] = reactExports.useState(null);
  reactExports.useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);
  const handleSave = async () => {
    const result = await validateConfig();
    if (result.valid) {
      await saveConfig();
    }
  };
  if (isLoading && !config) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-center h-full text-gray-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-6 h-6 animate-spin mr-2" }),
      "Loading LLM configuration..."
    ] });
  }
  if (error && !config) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col items-center justify-center h-full text-gray-400 gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-8 h-8 text-red-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-red-400", children: "Failed to load config" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-500", children: error }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: fetchConfig,
          className: "px-3 py-1.5 bg-engine-primary hover:bg-blue-600 rounded text-sm",
          children: "Retry"
        }
      )
    ] });
  }
  const roles = Object.keys(editedModels);
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-dark", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between px-4 py-3 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Cpu, { className: "w-5 h-5 text-engine-primary" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-sm font-semibold", children: "LLM Configuration" }),
        config?.source === "fallback" && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded", children: "Fallback" }),
        config?.source === "yaml" && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded", children: "YAML" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        lastSaved && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
          "Saved ",
          new Date(lastSaved).toLocaleTimeString()
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: reloadConfig,
            disabled: isLoading,
            className: "p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition",
            title: "Reload from YAML",
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(RefreshCw, { className: `w-4 h-4 ${isLoading ? "animate-spin" : ""}` })
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: resetChanges,
            disabled: !isDirty,
            className: `flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition ${isDirty ? "text-gray-300 hover:bg-gray-700" : "text-gray-600 cursor-not-allowed"}`,
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(RotateCcw, { className: "w-3.5 h-3.5" }),
              "Reset"
            ]
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: handleSave,
            disabled: !isDirty || isSaving,
            className: `flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition ${isDirty ? "bg-engine-primary hover:bg-blue-600 text-white" : "bg-gray-700 text-gray-500 cursor-not-allowed"}`,
            children: [
              isSaving ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 animate-spin" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Save, { className: "w-3.5 h-3.5" }),
              isSaving ? "Saving..." : "Save"
            ]
          }
        )
      ] })
    ] }),
    validation && !validation.valid && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mx-4 mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-red-400 text-sm font-medium mb-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-4 h-4" }),
        "Validation Failed"
      ] }),
      validation.errors.map((err, i) => /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-red-300 ml-6", children: err }, i))
    ] }),
    validation && validation.valid && validation.warnings.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mx-4 mt-3 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-yellow-400 text-sm font-medium mb-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: "w-4 h-4" }),
        "Warnings"
      ] }),
      validation.warnings.map((warn, i) => /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-yellow-300 ml-6", children: warn }, i))
    ] }),
    validation && validation.valid && validation.warnings.length === 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mx-4 mt-3 p-2 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-4 h-4 text-green-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-green-400", children: "Configuration saved successfully" })
    ] }),
    error && config && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mx-4 mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-4 h-4 text-red-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-red-400", children: error })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-auto p-4 space-y-2", children: roles.map((role) => {
      const meta = ROLE_META[role] || { label: role, icon: "⚙️", color: "text-gray-400" };
      const edited = editedModels[role];
      const original = config?.models[role];
      const isChanged = original && (original.model !== edited.model || original.provider !== edited.provider || original.max_tokens !== edited.max_tokens);
      const isExpanded = expandedRole === role;
      return /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "div",
        {
          className: `rounded-lg border transition ${isChanged ? "border-engine-primary/50 bg-engine-primary/5" : "border-gray-700 bg-engine-darker"}`,
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs(
              "button",
              {
                onClick: () => setExpandedRole(isExpanded ? null : role),
                className: "w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition rounded-lg",
                children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 min-w-0", children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-lg", children: meta.icon }),
                    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "min-w-0", children: [
                      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
                        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `text-sm font-medium ${meta.color}`, children: meta.label }),
                        isChanged && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px] px-1.5 py-0.5 bg-engine-primary/20 text-engine-primary rounded", children: "modified" })
                      ] }),
                      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500 truncate block", children: edited.model })
                    ] })
                  ] }),
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500 font-mono", children: edited.provider === "anthropic" ? "ANT" : "OR" }),
                    /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-600", children: [
                      (edited.max_tokens / 1024).toFixed(0),
                      "K"
                    ] }),
                    isExpanded ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronUp, { className: "w-4 h-4 text-gray-500" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-4 h-4 text-gray-500" })
                  ] })
                ]
              }
            ),
            isExpanded && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 pb-4 space-y-3 border-t border-gray-700/50 pt-3", children: [
              edited.description && /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 flex items-center gap-1.5", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-3 h-3" }),
                edited.description
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "text-xs text-gray-400 block mb-1", children: "Provider" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex gap-2", children: PROVIDER_OPTIONS.map((opt) => /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "button",
                  {
                    onClick: () => updateRole(role, "provider", opt.value),
                    className: `flex-1 px-3 py-2 rounded text-xs font-medium transition ${edited.provider === opt.value ? "bg-engine-primary/20 text-engine-primary border border-engine-primary/40" : "bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-500"}`,
                    children: opt.label
                  },
                  opt.value
                )) })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "text-xs text-gray-400 block mb-1", children: "Model ID" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "input",
                  {
                    type: "text",
                    value: edited.model,
                    onChange: (e) => updateRole(role, "model", e.target.value),
                    className: "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 focus:border-engine-primary focus:outline-none font-mono",
                    placeholder: edited.provider === "anthropic" ? "claude-sonnet-4-20250514" : "anthropic/claude-sonnet-4.5"
                  }
                ),
                /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-[10px] text-gray-600 mt-1", children: edited.provider === "anthropic" ? "Anthropic model name (no org/ prefix)" : "OpenRouter format: org/model-name" })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "text-xs text-gray-400 block mb-1", children: [
                  "Max Tokens (",
                  edited.max_tokens.toLocaleString(),
                  ")"
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex gap-1.5 flex-wrap", children: TOKEN_PRESETS.map((preset) => /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "button",
                  {
                    onClick: () => updateRole(role, "max_tokens", preset),
                    className: `px-2 py-1 rounded text-xs font-mono transition ${edited.max_tokens === preset ? "bg-engine-primary/20 text-engine-primary border border-engine-primary/40" : "bg-gray-800 text-gray-500 border border-gray-700 hover:border-gray-500"}`,
                    children: preset >= 1024 ? `${preset / 1024}K` : preset
                  },
                  preset
                )) })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-[10px] text-gray-600 bg-gray-800/50 rounded px-2 py-1.5 font-mono", children: [
                "Override: LLM_MODEL_",
                role.toUpperCase(),
                "=",
                edited.model
              ] })
            ] })
          ]
        },
        role
      );
    }) }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 py-2 border-t border-gray-700 flex items-center justify-between text-[10px] text-gray-600", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: config?.yaml_path && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-3 h-3 inline mr-1" }),
        config.yaml_path.split(/[/\\]/).slice(-2).join("/")
      ] }) }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
        roles.length,
        " roles configured"
      ] })
    ] })
  ] });
}
const COVERAGE_META = {
  requirements: { label: "Requirements", icon: "📋", color: "bg-blue-500" },
  user_stories: { label: "User Stories", icon: "👤", color: "bg-purple-500" },
  diagrams: { label: "Diagrams", icon: "📊", color: "bg-cyan-500" },
  dtos: { label: "DTOs", icon: "📦", color: "bg-green-500" },
  success_criteria: { label: "Success Criteria", icon: "✅", color: "bg-emerald-500" },
  test_scenarios: { label: "Test Scenarios", icon: "🧪", color: "bg-yellow-500" },
  component_specs: { label: "Component Specs", icon: "🧩", color: "bg-orange-500" },
  screen_specs: { label: "Screen Specs", icon: "🖥️", color: "bg-pink-500" },
  accessibility: { label: "Accessibility", icon: "♿", color: "bg-indigo-500" },
  design_tokens: { label: "Design Tokens", icon: "🎨", color: "bg-rose-500" },
  warnings: { label: "Warnings", icon: "⚠️", color: "bg-amber-500" }
};
const API_BASE$1 = "";
const useEnrichmentStore = create((set, get) => ({
  overview: null,
  tasks: [],
  selectedTask: null,
  schema: null,
  mapping: null,
  isLoading: false,
  error: null,
  activeEpicId: null,
  projectPath: null,
  filterType: null,
  setProjectPath: (path) => {
    set({ projectPath: path, overview: null, tasks: [], selectedTask: null, schema: null, mapping: null });
  },
  fetchOverview: async (epicId) => {
    const { projectPath } = get();
    if (!projectPath) {
      set({ error: "No project path set" });
      return;
    }
    set({ isLoading: true, error: null, activeEpicId: epicId });
    try {
      const params = new URLSearchParams({ project_path: projectPath });
      const response = await fetch(`${API_BASE$1}/api/v1/enrichment/overview/${epicId}?${params}`);
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
        throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      }
      const data = await response.json();
      set({ overview: data, isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: String(error) });
    }
  },
  fetchTasks: async (epicId, taskType) => {
    const { projectPath } = get();
    if (!projectPath) return;
    set({ isLoading: true, error: null });
    try {
      const params = new URLSearchParams({ project_path: projectPath });
      if (taskType) params.set("task_type", taskType);
      const response = await fetch(`${API_BASE$1}/api/v1/enrichment/tasks/${epicId}?${params}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      set({ tasks: data, isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: String(error) });
    }
  },
  fetchTaskDetail: async (epicId, taskId) => {
    const { projectPath } = get();
    if (!projectPath) return;
    set({ isLoading: true, error: null });
    try {
      const params = new URLSearchParams({ project_path: projectPath });
      const response = await fetch(`${API_BASE$1}/api/v1/enrichment/task/${epicId}/${taskId}?${params}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      set({ selectedTask: data, isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: String(error) });
    }
  },
  fetchSchema: async () => {
    const { projectPath } = get();
    if (!projectPath) return;
    try {
      const params = new URLSearchParams({ project_path: projectPath });
      const response = await fetch(`${API_BASE$1}/api/v1/enrichment/schema?${params}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      set({ schema: data });
    } catch (error) {
      set({ error: String(error) });
    }
  },
  fetchMapping: async () => {
    const { projectPath } = get();
    if (!projectPath) return;
    try {
      const params = new URLSearchParams({ project_path: projectPath });
      const response = await fetch(`${API_BASE$1}/api/v1/enrichment/mapping?${params}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      set({ mapping: data });
    } catch (error) {
      set({ error: String(error) });
    }
  },
  setFilterType: (type) => {
    const { activeEpicId } = get();
    set({ filterType: type });
    if (activeEpicId) {
      get().fetchTasks(activeEpicId, type || void 0);
    }
  },
  clearSelection: () => {
    set({ selectedTask: null });
  }
}));
function EnrichmentView() {
  const {
    overview,
    tasks,
    selectedTask,
    schema,
    mapping,
    isLoading,
    error,
    activeEpicId,
    projectPath,
    filterType,
    setProjectPath,
    fetchOverview,
    fetchTasks,
    fetchTaskDetail,
    fetchSchema,
    fetchMapping,
    setFilterType,
    clearSelection
  } = useEnrichmentStore();
  const { epics, currentProjectPath } = useEngineStore();
  const [subTab, setSubTab] = reactExports.useState("overview");
  const [epicInput, setEpicInput] = reactExports.useState("");
  const [searchQuery, setSearchQuery] = reactExports.useState("");
  reactExports.useEffect(() => {
    if (currentProjectPath && currentProjectPath !== projectPath) {
      setProjectPath(currentProjectPath);
    }
  }, [currentProjectPath, projectPath, setProjectPath]);
  reactExports.useEffect(() => {
    if (epics.length > 0 && !activeEpicId && projectPath) {
      const firstEpicId = epics[0]?.id;
      if (firstEpicId) {
        handleLoadEpic(firstEpicId);
      }
    }
  }, [epics, activeEpicId, projectPath]);
  const handleLoadEpic = async (epicId) => {
    await fetchOverview(epicId);
    await fetchTasks(epicId);
    fetchSchema();
    fetchMapping();
  };
  const handleEpicSubmit = () => {
    if (epicInput.trim()) {
      handleLoadEpic(epicInput.trim());
    }
  };
  const filteredTasks = tasks.filter((t2) => {
    if (searchQuery) {
      const q2 = searchQuery.toLowerCase();
      return t2.title.toLowerCase().includes(q2) || t2.id.toLowerCase().includes(q2);
    }
    return true;
  });
  if (!projectPath) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col items-center justify-center h-full text-gray-400 gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(BookOpen, { className: "w-8 h-8 text-gray-500" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "Select a project to view enrichment data" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-600", children: "Load a project in the Epics tab first" })
    ] });
  }
  if (selectedTask) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-dark", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 px-4 py-3 border-b border-gray-700", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: clearSelection,
            className: "p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition",
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(ArrowLeft, { className: "w-4 h-4" })
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-sm font-semibold truncate", children: selectedTask.title }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-gray-700 text-gray-300 rounded ml-auto", children: selectedTask.type })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto p-4 space-y-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-3 text-xs", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: "ID" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "font-mono text-gray-300 mt-0.5", children: selectedTask.id })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: "Status" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-300 mt-0.5 capitalize", children: selectedTask.status })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Description" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-300 mt-1 whitespace-pre-wrap", children: selectedTask.description || "No description" })
        ] }),
        selectedTask.dependencies.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
            "Dependencies (",
            selectedTask.dependencies.length,
            ")"
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5 mt-1.5", children: selectedTask.dependencies.map((dep) => /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs font-mono px-2 py-0.5 bg-gray-700 text-gray-300 rounded", children: dep }, dep)) })
        ] }),
        selectedTask.related_requirements.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
            "Related Requirements (",
            selectedTask.related_requirements.length,
            ")"
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5 mt-1.5", children: selectedTask.related_requirements.map((req) => /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded", children: req }, req)) })
        ] }),
        selectedTask.related_user_stories.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
            "User Stories (",
            selectedTask.related_user_stories.length,
            ")"
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5 mt-1.5", children: selectedTask.related_user_stories.map((us) => /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded", children: us }, us)) })
        ] }),
        selectedTask.success_criteria && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Success Criteria" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-300 mt-1 whitespace-pre-wrap", children: selectedTask.success_criteria })
        ] }),
        selectedTask.enrichment_context && Object.keys(selectedTask.enrichment_context).length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Enrichment Context" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("pre", { className: "text-xs text-gray-400 mt-1 overflow-auto max-h-60 font-mono", children: JSON.stringify(selectedTask.enrichment_context, null, 2) })
        ] })
      ] })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-dark", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between px-4 py-3 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(BookOpen, { className: "w-5 h-5 text-cyan-400" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-sm font-semibold", children: "Enrichment Pipeline" }),
        activeEpicId && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-cyan-500/20 text-cyan-400 rounded", children: activeEpicId })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex items-center gap-2", children: epics.length > 0 ? /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "select",
        {
          value: activeEpicId || "",
          onChange: (e) => e.target.value && handleLoadEpic(e.target.value),
          className: "text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 focus:border-cyan-500 focus:outline-none",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: "", children: "Select Epic..." }),
            epics.map((epic) => /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: epic.id, children: epic.name || epic.id }, epic.id))
          ]
        }
      ) : /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "input",
          {
            type: "text",
            value: epicInput,
            onChange: (e) => setEpicInput(e.target.value),
            onKeyDown: (e) => e.key === "Enter" && handleEpicSubmit(),
            placeholder: "Epic ID...",
            className: "text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 w-32 focus:border-cyan-500 focus:outline-none"
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: handleEpicSubmit,
            disabled: !epicInput.trim(),
            className: "px-2 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs text-white transition",
            children: "Load"
          }
        )
      ] }) })
    ] }),
    activeEpicId && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex border-b border-gray-700/50 px-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(SubTabButton, { active: subTab === "overview", onClick: () => setSubTab("overview"), icon: /* @__PURE__ */ jsxRuntimeExports.jsx(BarChart3, { className: "w-3.5 h-3.5" }), label: "Overview" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(SubTabButton, { active: subTab === "tasks", onClick: () => setSubTab("tasks"), icon: /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-3.5 h-3.5" }), label: `Tasks${tasks.length > 0 ? ` (${tasks.length})` : ""}` }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(SubTabButton, { active: subTab === "schema", onClick: () => setSubTab("schema"), icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Database, { className: "w-3.5 h-3.5" }), label: "Schema" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(SubTabButton, { active: subTab === "mapping", onClick: () => setSubTab("mapping"), icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Map$1, { className: "w-3.5 h-3.5" }), label: "Mapping" })
    ] }),
    error && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mx-4 mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-4 h-4 text-red-400 flex-shrink-0" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-red-400 truncate", children: error })
    ] }),
    isLoading && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-center py-8 text-gray-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-5 h-5 animate-spin mr-2" }),
      "Loading enrichment data..."
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto p-4", children: [
      !activeEpicId && !isLoading && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col items-center justify-center h-full text-gray-500 gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(BarChart3, { className: "w-8 h-8" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm", children: "Select an epic to view enrichment" })
      ] }),
      activeEpicId && !isLoading && subTab === "overview" && overview && /* @__PURE__ */ jsxRuntimeExports.jsx(OverviewPanel, { overview }),
      activeEpicId && !isLoading && subTab === "tasks" && /* @__PURE__ */ jsxRuntimeExports.jsx(
        TasksPanel,
        {
          tasks: filteredTasks,
          filterType,
          searchQuery,
          typeDistribution: overview?.task_type_distribution || {},
          onFilterType: setFilterType,
          onSearchChange: setSearchQuery,
          onSelectTask: (t2) => fetchTaskDetail(activeEpicId, t2.id)
        }
      ),
      activeEpicId && !isLoading && subTab === "schema" && /* @__PURE__ */ jsxRuntimeExports.jsx(SchemaPanel, { schema }),
      activeEpicId && !isLoading && subTab === "mapping" && /* @__PURE__ */ jsxRuntimeExports.jsx(MappingPanel, { mapping })
    ] })
  ] });
}
function SubTabButton({ active, onClick, icon, label }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "button",
    {
      onClick,
      className: `flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition border-b-2 ${active ? "text-cyan-400 border-cyan-400" : "text-gray-500 border-transparent hover:text-gray-300"}`,
      children: [
        icon,
        label
      ]
    }
  );
}
function OverviewPanel({ overview }) {
  const coverageEntries = Object.entries(overview.enrichment_coverage).filter(
    ([key]) => key in COVERAGE_META
  );
  const avgCoverage = coverageEntries.length > 0 ? coverageEntries.reduce((sum, [, v2]) => sum + v2, 0) / coverageEntries.length : 0;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-4", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-3 gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatCard, { label: "Total Tasks", value: overview.stats.total_tasks }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        StatCard,
        {
          label: "Avg Coverage",
          value: `${(avgCoverage * 100).toFixed(0)}%`,
          color: avgCoverage >= 0.7 ? "text-green-400" : avgCoverage >= 0.4 ? "text-yellow-400" : "text-red-400"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        StatCard,
        {
          label: "Enriched",
          value: overview.enrichment_timestamp ? new Date(overview.enrichment_timestamp).toLocaleDateString() : "N/A"
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-xs font-medium text-gray-400 mb-3", children: "Enrichment Coverage" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2.5", children: coverageEntries.map(([key, value]) => {
        const meta = COVERAGE_META[key];
        if (!meta) return null;
        const pct = Math.round(value * 100);
        return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm w-5 text-center", children: meta.icon }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-400 w-28 truncate", children: meta.label }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 h-2 bg-gray-700 rounded-full overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: `h-full ${meta.color} rounded-full transition-all duration-300`,
              style: { width: `${pct}%` }
            }
          ) }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: `text-xs font-mono w-10 text-right ${pct >= 70 ? "text-green-400" : pct >= 40 ? "text-yellow-400" : "text-gray-500"}`, children: [
            pct,
            "%"
          ] })
        ] }, key);
      }) })
    ] }),
    Object.keys(overview.task_type_distribution).length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-xs font-medium text-gray-400 mb-3", children: "Task Type Distribution" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-2", children: Object.entries(overview.task_type_distribution).sort(([, a], [, b]) => b - a).map(([type, count]) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "span",
        {
          className: "text-xs px-2.5 py-1 bg-gray-700 text-gray-300 rounded-full",
          children: [
            type,
            " ",
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500 ml-1", children: count })
          ]
        },
        type
      )) })
    ] })
  ] });
}
function StatCard({ label, value, color }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3 text-center", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-500", children: label }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: `text-lg font-semibold mt-0.5 ${color || "text-gray-200"}`, children: value })
  ] });
}
function TasksPanel({
  tasks,
  filterType,
  searchQuery,
  typeDistribution,
  onFilterType,
  onSearchChange,
  onSelectTask
}) {
  const types = Object.keys(typeDistribution);
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-3", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative flex-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Search, { className: "w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "input",
          {
            type: "text",
            value: searchQuery,
            onChange: (e) => onSearchChange(e.target.value),
            placeholder: "Search tasks...",
            className: "w-full pl-8 pr-3 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 focus:border-cyan-500 focus:outline-none"
          }
        )
      ] }),
      types.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Filter, { className: "w-3.5 h-3.5 text-gray-500" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "select",
          {
            value: filterType || "",
            onChange: (e) => onFilterType(e.target.value || null),
            className: "text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 focus:border-cyan-500 focus:outline-none",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: "", children: "All types" }),
              types.map((t2) => /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: t2, children: t2 }, t2))
            ]
          }
        )
      ] })
    ] }),
    tasks.length === 0 ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-center text-gray-500 text-sm py-8", children: "No tasks found" }) : /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-1.5", children: tasks.map((task) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: () => onSelectTask(task),
        className: "w-full flex items-center gap-3 px-3 py-2.5 bg-engine-darker hover:bg-gray-700/50 rounded-lg transition text-left group",
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative w-8 h-8 flex-shrink-0", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("svg", { className: "w-8 h-8 -rotate-90", viewBox: "0 0 36 36", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("circle", { cx: "18", cy: "18", r: "14", fill: "none", stroke: "#374151", strokeWidth: "3" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "circle",
                {
                  cx: "18",
                  cy: "18",
                  r: "14",
                  fill: "none",
                  stroke: task.enrichment_score >= 0.7 ? "#22c55e" : task.enrichment_score >= 0.4 ? "#eab308" : "#6b7280",
                  strokeWidth: "3",
                  strokeDasharray: `${task.enrichment_score * 88} 88`,
                  strokeLinecap: "round"
                }
              )
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "absolute inset-0 flex items-center justify-center text-[9px] font-mono text-gray-400", children: Math.round(task.enrichment_score * 100) })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex items-center gap-2", children: /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-200 truncate", children: task.title }) }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 mt-0.5", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px] font-mono text-gray-600", children: task.id }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px] px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded", children: task.type }),
              task.has_warnings && /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: "w-3 h-3 text-yellow-500" })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 flex-shrink-0", children: [
            task.has_requirements && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "Requirements", children: "📋" }),
            task.has_user_stories && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "User Stories", children: "👤" }),
            task.has_diagrams && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "Diagrams", children: "📊" }),
            task.has_test_scenarios && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "Tests", children: "🧪" }),
            task.has_component_spec && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "Component", children: "🧩" }),
            task.has_accessibility && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "A11y", children: "♿" }),
            task.has_design_tokens && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-[10px]", title: "Tokens", children: "🎨" })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronRight, { className: "w-4 h-4 text-gray-600 group-hover:text-gray-400 flex-shrink-0" })
        ]
      },
      task.id
    )) })
  ] });
}
function SchemaPanel({ schema }) {
  if (!schema || schema.source_count === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center text-gray-500 text-sm py-8", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Database, { className: "w-6 h-6 mx-auto mb-2 text-gray-600" }),
      "No schema discovery data available",
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-600 mt-1", children: "Run enrichment pipeline first" })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-4", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Project" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-200 mt-0.5", children: schema.project_name || "Unknown" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Language" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-200 mt-0.5", children: schema.language || "Unknown" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Requirement Pattern" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-200 font-mono mt-0.5", children: schema.requirement_id_pattern || "N/A" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Sources Discovered" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-200 mt-0.5", children: schema.source_count })
      ] })
    ] }),
    Object.keys(schema.sources).length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-xs font-medium text-gray-400 mb-3", children: "Discovered Sources" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2", children: Object.entries(schema.sources).map(([key, value]) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "min-w-0", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs font-medium text-gray-300", children: key }),
          typeof value === "object" && value !== null && /* @__PURE__ */ jsxRuntimeExports.jsx("pre", { className: "text-[10px] text-gray-500 mt-0.5 truncate", children: JSON.stringify(value).slice(0, 120) })
        ] })
      ] }, key)) })
    ] }),
    schema.schema_hash && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-[10px] text-gray-600 font-mono px-1", children: [
      "Schema hash: ",
      schema.schema_hash
    ] })
  ] });
}
function MappingPanel({ mapping }) {
  if (!mapping || mapping.total_mappings === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center text-gray-500 text-sm py-8", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Map$1, { className: "w-6 h-6 mx-auto mb-2 text-gray-600" }),
      "No task mapping data available",
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-600 mt-1", children: "Run enrichment pipeline first" })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-4", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatCard, { label: "Total Mappings", value: mapping.total_mappings }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        StatCard,
        {
          label: "LLM-Assisted",
          value: mapping.llm_used ? "Yes" : "Heuristic",
          color: mapping.llm_used ? "text-cyan-400" : "text-gray-400"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatCard, { label: "With Types", value: mapping.tasks_with_types }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatCard, { label: "With Requirements", value: mapping.tasks_with_requirements })
    ] }),
    Object.keys(mapping.type_distribution).length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker rounded-lg p-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-xs font-medium text-gray-400 mb-3", children: "Inferred Type Distribution" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2", children: Object.entries(mapping.type_distribution).sort(([, a], [, b]) => b - a).map(([type, count]) => {
        const maxCount = Math.max(...Object.values(mapping.type_distribution));
        const pct = Math.round(count / maxCount * 100);
        return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-400 w-28 truncate font-mono", children: type }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 h-2 bg-gray-700 rounded-full overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: "h-full bg-cyan-500 rounded-full transition-all",
              style: { width: `${pct}%` }
            }
          ) }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs font-mono text-gray-500 w-8 text-right", children: count })
        ] }, type);
      }) })
    ] })
  ] });
}
function buildDependencyGraph(tasks) {
  const taskMap = /* @__PURE__ */ new Map();
  tasks.forEach((t2) => taskMap.set(t2.id, t2));
  const blocksMap = /* @__PURE__ */ new Map();
  tasks.forEach((t2) => {
    t2.dependencies.forEach((depId) => {
      if (!blocksMap.has(depId)) blocksMap.set(depId, []);
      blocksMap.get(depId).push(t2.id);
    });
  });
  const depths = /* @__PURE__ */ new Map();
  const queue = [];
  tasks.forEach((t2) => {
    if (t2.dependencies.length === 0) {
      depths.set(t2.id, 0);
      queue.push(t2.id);
    }
  });
  while (queue.length > 0) {
    const current = queue.shift();
    const currentDepth = depths.get(current) || 0;
    const children = blocksMap.get(current) || [];
    children.forEach((childId) => {
      const existingDepth = depths.get(childId) || 0;
      if (currentDepth + 1 > existingDepth) {
        depths.set(childId, currentDepth + 1);
      }
      if (!queue.includes(childId)) {
        queue.push(childId);
      }
    });
  }
  const maxDepth = Math.max(0, ...Array.from(depths.values()));
  tasks.forEach((t2) => {
    if (!depths.has(t2.id)) depths.set(t2.id, maxDepth + 1);
  });
  const isBlocked = (task) => {
    return task.dependencies.filter((depId) => {
      const dep = taskMap.get(depId);
      return dep && dep.status !== "completed" && dep.status !== "skipped";
    });
  };
  const criticalPathIds = findCriticalPath(tasks, taskMap, blocksMap);
  const nodes = /* @__PURE__ */ new Map();
  tasks.forEach((t2) => {
    const blockedByIds = isBlocked(t2);
    nodes.set(t2.id, {
      task: t2,
      depth: depths.get(t2.id) || 0,
      blocked: blockedByIds.length > 0 && t2.status === "pending",
      blockedBy: blockedByIds,
      blocks: blocksMap.get(t2.id) || [],
      criticalPath: criticalPathIds.has(t2.id)
    });
  });
  return nodes;
}
function findCriticalPath(tasks, taskMap, blocksMap) {
  const memo = /* @__PURE__ */ new Map();
  function longestPath(taskId) {
    if (memo.has(taskId)) return memo.get(taskId);
    const children = blocksMap.get(taskId) || [];
    if (children.length === 0) {
      memo.set(taskId, 1);
      return 1;
    }
    const max = 1 + Math.max(...children.map((c) => longestPath(c)));
    memo.set(taskId, max);
    return max;
  }
  const roots = tasks.filter((t2) => t2.dependencies.length === 0);
  let maxLen = 0;
  let bestRoot = "";
  roots.forEach((r2) => {
    const len = longestPath(r2.id);
    if (len > maxLen) {
      maxLen = len;
      bestRoot = r2.id;
    }
  });
  const path = /* @__PURE__ */ new Set();
  function trace(id2) {
    path.add(id2);
    const children = blocksMap.get(id2) || [];
    if (children.length === 0) return;
    let bestChild = children[0];
    let bestLen = 0;
    children.forEach((c) => {
      const len = memo.get(c) || 0;
      if (len > bestLen) {
        bestLen = len;
        bestChild = c;
      }
    });
    if (bestChild) trace(bestChild);
  }
  if (bestRoot) trace(bestRoot);
  return path;
}
function getStatusIcon(status, blocked) {
  if (blocked) return /* @__PURE__ */ jsxRuntimeExports.jsx(Lock, { className: "w-3.5 h-3.5 text-orange-500" });
  switch (status) {
    case "completed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-3.5 h-3.5 text-green-500" });
    case "failed":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-3.5 h-3.5 text-red-500" });
    case "running":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 text-yellow-500 animate-spin" });
    case "skipped":
      return /* @__PURE__ */ jsxRuntimeExports.jsx(SkipForward, { className: "w-3.5 h-3.5 text-gray-500" });
    default:
      return /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-3.5 h-3.5 text-gray-500" });
  }
}
function getStatusColor(status, blocked) {
  if (blocked) return "border-orange-500/40 bg-orange-500/5";
  switch (status) {
    case "completed":
      return "border-green-500/40 bg-green-500/5";
    case "failed":
      return "border-red-500/40 bg-red-500/5";
    case "running":
      return "border-yellow-500/40 bg-yellow-500/5";
    case "skipped":
      return "border-gray-600 bg-gray-800";
    default:
      return "border-gray-700 bg-engine-darker";
  }
}
const TYPE_COLORS = {
  schema: "bg-blue-500/20 text-blue-400",
  schema_migration: "bg-blue-500/20 text-blue-400",
  api: "bg-green-500/20 text-green-400",
  api_endpoint: "bg-green-500/20 text-green-400",
  frontend: "bg-purple-500/20 text-purple-400",
  fe_component: "bg-purple-500/20 text-purple-400",
  fe_page: "bg-purple-500/20 text-purple-400",
  test: "bg-yellow-500/20 text-yellow-400",
  test_e2e: "bg-yellow-500/20 text-yellow-400",
  integration: "bg-cyan-500/20 text-cyan-400",
  verify: "bg-orange-500/20 text-orange-400",
  docker: "bg-pink-500/20 text-pink-400",
  config: "bg-gray-500/20 text-gray-400"
};
function TaskDependencyBoard() {
  const { epicTaskLists, epics } = useEngineStore();
  const [selectedEpicId, setSelectedEpicId] = reactExports.useState(null);
  const [viewMode, setViewMode] = reactExports.useState("board");
  const [statusFilter, setStatusFilter] = reactExports.useState("all");
  const [searchQuery, setSearchQuery] = reactExports.useState("");
  const [selectedTaskId, setSelectedTaskId] = reactExports.useState(null);
  const [hoveredTaskId, setHoveredTaskId] = reactExports.useState(null);
  const activeEpicId = selectedEpicId || Object.keys(epicTaskLists)[0] || null;
  const taskList = activeEpicId ? epicTaskLists[activeEpicId] : null;
  const tasks = taskList?.tasks || [];
  const graph = reactExports.useMemo(() => buildDependencyGraph(tasks), [tasks]);
  const stats = reactExports.useMemo(() => {
    const nodes = Array.from(graph.values());
    return {
      total: nodes.length,
      completed: nodes.filter((n2) => n2.task.status === "completed").length,
      running: nodes.filter((n2) => n2.task.status === "running").length,
      failed: nodes.filter((n2) => n2.task.status === "failed").length,
      blocked: nodes.filter((n2) => n2.blocked).length,
      pending: nodes.filter((n2) => n2.task.status === "pending" && !n2.blocked).length,
      maxDepth: Math.max(0, ...nodes.map((n2) => n2.depth)),
      criticalPathLen: nodes.filter((n2) => n2.criticalPath).length
    };
  }, [graph]);
  const filteredNodes = reactExports.useMemo(() => {
    let nodes = Array.from(graph.values());
    if (statusFilter === "blocked") {
      nodes = nodes.filter((n2) => n2.blocked);
    } else if (statusFilter !== "all") {
      nodes = nodes.filter((n2) => n2.task.status === statusFilter);
    }
    if (searchQuery) {
      const q2 = searchQuery.toLowerCase();
      nodes = nodes.filter(
        (n2) => n2.task.title.toLowerCase().includes(q2) || n2.task.id.toLowerCase().includes(q2)
      );
    }
    return nodes;
  }, [graph, statusFilter, searchQuery]);
  const highlightedIds = reactExports.useMemo(() => {
    if (!hoveredTaskId) return /* @__PURE__ */ new Set();
    const node = graph.get(hoveredTaskId);
    if (!node) return /* @__PURE__ */ new Set();
    const ids = /* @__PURE__ */ new Set([hoveredTaskId]);
    node.task.dependencies.forEach((d) => ids.add(d));
    node.blocks.forEach((b) => ids.add(b));
    return ids;
  }, [hoveredTaskId, graph]);
  if (tasks.length === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-dark", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 px-4 py-3 border-b border-gray-700", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-5 h-5 text-indigo-400" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-sm font-semibold", children: "Task Board" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 flex items-center justify-center text-gray-500", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-8 h-8 mx-auto mb-2 text-gray-600" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm", children: "No task data loaded" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-600 mt-1", children: "Load an epic in the Epics tab to see tasks" })
      ] }) })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-dark", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between px-4 py-3 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-5 h-5 text-indigo-400" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-sm font-semibold", children: "Task Board" }),
        activeEpicId && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs px-2 py-0.5 bg-indigo-500/20 text-indigo-400 rounded", children: taskList?.epic_name || activeEpicId })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        Object.keys(epicTaskLists).length > 1 && /* @__PURE__ */ jsxRuntimeExports.jsx(
          "select",
          {
            value: activeEpicId || "",
            onChange: (e) => setSelectedEpicId(e.target.value || null),
            className: "text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 focus:border-indigo-500 focus:outline-none",
            children: Object.entries(epicTaskLists).map(([id2, tl2]) => /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: id2, children: tl2.epic_name || id2 }, id2))
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex bg-gray-800 rounded border border-gray-700", children: ["board", "graph", "list"].map((mode) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: () => setViewMode(mode),
            className: `px-2.5 py-1 text-xs capitalize transition ${viewMode === mode ? "bg-indigo-500/20 text-indigo-400" : "text-gray-500 hover:text-gray-300"}`,
            children: mode
          },
          mode
        )) })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 px-4 py-2 border-b border-gray-700/50 text-[10px]", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatPill, { label: "Total", value: stats.total, color: "text-gray-300" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatPill, { label: "Done", value: stats.completed, color: "text-green-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatPill, { label: "Running", value: stats.running, color: "text-yellow-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatPill, { label: "Pending", value: stats.pending, color: "text-gray-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatPill, { label: "Blocked", value: stats.blocked, color: "text-orange-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StatPill, { label: "Failed", value: stats.failed, color: "text-red-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "ml-auto flex items-center gap-1 text-gray-500", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Zap, { className: "w-3 h-3 text-indigo-400" }),
        "Critical path: ",
        stats.criticalPathLen,
        " tasks, ",
        stats.maxDepth + 1,
        " layers"
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 px-4 py-2 border-b border-gray-700/50", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative flex-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Search, { className: "w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "input",
          {
            type: "text",
            value: searchQuery,
            onChange: (e) => setSearchQuery(e.target.value),
            placeholder: "Search tasks...",
            className: "w-full pl-8 pr-3 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 focus:border-indigo-500 focus:outline-none"
          }
        )
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Filter, { className: "w-3.5 h-3.5 text-gray-500" }),
        ["all", "pending", "running", "completed", "failed", "blocked"].map((f2) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: () => setStatusFilter(f2),
            className: `px-2 py-1 text-[10px] rounded capitalize transition ${statusFilter === f2 ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/40" : "text-gray-500 hover:text-gray-300 border border-transparent"}`,
            children: f2
          },
          f2
        ))
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto p-4", children: [
      viewMode === "board" && /* @__PURE__ */ jsxRuntimeExports.jsx(
        BoardView,
        {
          nodes: filteredNodes,
          graph,
          highlightedIds,
          selectedTaskId,
          onSelectTask: setSelectedTaskId,
          onHoverTask: setHoveredTaskId,
          maxDepth: stats.maxDepth
        }
      ),
      viewMode === "graph" && /* @__PURE__ */ jsxRuntimeExports.jsx(
        GraphView,
        {
          nodes: Array.from(graph.values()),
          highlightedIds,
          onHoverTask: setHoveredTaskId,
          onSelectTask: setSelectedTaskId
        }
      ),
      viewMode === "list" && /* @__PURE__ */ jsxRuntimeExports.jsx(
        ListView,
        {
          nodes: filteredNodes,
          highlightedIds,
          selectedTaskId,
          onSelectTask: setSelectedTaskId,
          onHoverTask: setHoveredTaskId
        }
      )
    ] }),
    selectedTaskId && graph.has(selectedTaskId) && /* @__PURE__ */ jsxRuntimeExports.jsx(
      TaskDetailPanel,
      {
        node: graph.get(selectedTaskId),
        graph,
        onClose: () => setSelectedTaskId(null),
        onNavigate: setSelectedTaskId
      }
    )
  ] });
}
function StatPill({ label, value, color }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-1", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: label }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `font-mono font-medium ${color}`, children: value })
  ] });
}
function BoardView({
  nodes,
  graph,
  highlightedIds,
  selectedTaskId,
  onSelectTask,
  onHoverTask,
  maxDepth
}) {
  const layers = reactExports.useMemo(() => {
    const layerMap = /* @__PURE__ */ new Map();
    nodes.forEach((n2) => {
      if (!layerMap.has(n2.depth)) layerMap.set(n2.depth, []);
      layerMap.get(n2.depth).push(n2);
    });
    return Array.from(layerMap.entries()).sort(([a], [b]) => a - b);
  }, [nodes]);
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-4", children: layers.map(([depth, layerNodes]) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 mb-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[10px] font-medium text-gray-500 uppercase", children: [
        "Layer ",
        depth
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[10px] text-gray-600", children: [
        layerNodes.length,
        " tasks"
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 h-px bg-gray-700/50" })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2", children: layerNodes.map((node) => /* @__PURE__ */ jsxRuntimeExports.jsx(
      TaskCard,
      {
        node,
        isHighlighted: highlightedIds.has(node.task.id),
        isSelected: selectedTaskId === node.task.id,
        isDimmed: highlightedIds.size > 0 && !highlightedIds.has(node.task.id),
        onClick: () => onSelectTask(selectedTaskId === node.task.id ? null : node.task.id),
        onMouseEnter: () => onHoverTask(node.task.id),
        onMouseLeave: () => onHoverTask(null)
      },
      node.task.id
    )) })
  ] }, depth)) });
}
function GraphView({
  nodes,
  highlightedIds,
  onHoverTask,
  onSelectTask
}) {
  const layers = reactExports.useMemo(() => {
    const layerMap = /* @__PURE__ */ new Map();
    nodes.forEach((n2) => {
      if (!layerMap.has(n2.depth)) layerMap.set(n2.depth, []);
      layerMap.get(n2.depth).push(n2);
    });
    return Array.from(layerMap.entries()).sort(([a], [b]) => a - b);
  }, [nodes]);
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "overflow-auto", children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex gap-6 min-w-max pb-4", children: layers.map(([depth, layerNodes], layerIdx) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col items-center gap-2 min-w-[180px]", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-[10px] font-medium text-gray-500 uppercase mb-1", children: [
      "Layer ",
      depth
    ] }),
    layerNodes.map((node) => {
      const isHL = highlightedIds.has(node.task.id);
      const isDim = highlightedIds.size > 0 && !isHL;
      return /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "div",
        {
          className: `relative w-full px-3 py-2 rounded-lg border text-xs cursor-pointer transition ${getStatusColor(node.task.status, node.blocked)} ${node.criticalPath ? "ring-1 ring-indigo-500/40" : ""} ${isDim ? "opacity-30" : ""} ${isHL ? "ring-2 ring-indigo-400" : ""}`,
          onMouseEnter: () => onHoverTask(node.task.id),
          onMouseLeave: () => onHoverTask(null),
          onClick: () => onSelectTask(node.task.id),
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5 mb-1", children: [
              getStatusIcon(node.task.status, node.blocked),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-mono text-[9px] text-gray-500", children: node.task.id })
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-300 truncate", children: node.task.title }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 mt-1", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `text-[9px] px-1 py-0.5 rounded ${TYPE_COLORS[node.task.type] || "bg-gray-700 text-gray-400"}`, children: node.task.type }),
              node.task.dependencies.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[9px] text-gray-600", children: [
                "← ",
                node.task.dependencies.length,
                " deps"
              ] }),
              node.blocks.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[9px] text-gray-600", children: [
                "→ ",
                node.blocks.length,
                " blocks"
              ] })
            ] })
          ]
        },
        node.task.id
      );
    }),
    layerIdx < layers.length - 1 && layerNodes.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx(ArrowRight, { className: "w-4 h-4 text-gray-600 mt-2" })
  ] }, depth)) }) });
}
function ListView({
  nodes,
  highlightedIds,
  selectedTaskId,
  onSelectTask,
  onHoverTask
}) {
  const sorted = reactExports.useMemo(() => {
    const priority = {
      running: 0,
      failed: 1,
      pending: 2,
      completed: 3,
      skipped: 4
    };
    return [...nodes].sort((a, b) => {
      const aP = a.blocked ? 1.5 : priority[a.task.status] ?? 5;
      const bP = b.blocked ? 1.5 : priority[b.task.status] ?? 5;
      return aP - bP;
    });
  }, [nodes]);
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-1", children: sorted.map((node) => /* @__PURE__ */ jsxRuntimeExports.jsx(
    TaskCard,
    {
      node,
      isHighlighted: highlightedIds.has(node.task.id),
      isSelected: selectedTaskId === node.task.id,
      isDimmed: highlightedIds.size > 0 && !highlightedIds.has(node.task.id),
      onClick: () => onSelectTask(selectedTaskId === node.task.id ? null : node.task.id),
      onMouseEnter: () => onHoverTask(node.task.id),
      onMouseLeave: () => onHoverTask(null)
    },
    node.task.id
  )) });
}
function TaskCard({
  node,
  isHighlighted,
  isSelected,
  isDimmed,
  onClick,
  onMouseEnter,
  onMouseLeave
}) {
  const { task, blocked, blockedBy, blocks, criticalPath } = node;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "button",
    {
      onClick,
      onMouseEnter,
      onMouseLeave,
      className: `w-full text-left px-3 py-2.5 rounded-lg border transition ${getStatusColor(task.status, blocked)} ${criticalPath ? "ring-1 ring-indigo-500/30" : ""} ${isSelected ? "ring-2 ring-indigo-400" : ""} ${isHighlighted ? "ring-2 ring-indigo-400/60" : ""} ${isDimmed ? "opacity-30" : ""} hover:bg-white/5`,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
          getStatusIcon(task.status, blocked),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-200 truncate flex-1", children: task.title }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `text-[10px] px-1.5 py-0.5 rounded ${TYPE_COLORS[task.type] || "bg-gray-700 text-gray-400"}`, children: task.type })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 mt-1 text-[10px]", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-mono text-gray-600", children: task.id }),
          blocked && blockedBy.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-orange-400 flex items-center gap-0.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Lock, { className: "w-2.5 h-2.5" }),
            "Blocked by ",
            blockedBy.length
          ] }),
          blocks.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-gray-500 flex items-center gap-0.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Unlock, { className: "w-2.5 h-2.5" }),
            "Blocks ",
            blocks.length
          ] }),
          criticalPath && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-indigo-400 flex items-center gap-0.5", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Zap, { className: "w-2.5 h-2.5" }),
            "Critical"
          ] }),
          task.error_message && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400 truncate ml-auto max-w-[200px]", children: task.error_message })
        ] })
      ]
    }
  );
}
function TaskDetailPanel({
  node,
  graph,
  onClose,
  onNavigate
}) {
  const { task, blocked, blockedBy, blocks, depth, criticalPath } = node;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "border-t border-gray-700 bg-engine-darker px-4 py-3 max-h-72 overflow-auto", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between mb-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        getStatusIcon(task.status, blocked),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-sm font-medium text-gray-200", children: task.title })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("button", { onClick: onClose, className: "text-gray-500 hover:text-gray-300 text-xs", children: "✕" })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-3 gap-2 text-xs mb-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: "ID" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "font-mono text-gray-300", children: task.id })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: "Type" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-300", children: task.type })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: "Layer" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-gray-300", children: [
          depth,
          " ",
          criticalPath ? "(critical path)" : ""
        ] })
      ] })
    ] }),
    task.description && /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-400 mb-3 line-clamp-2", children: task.description }),
    task.dependencies.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mb-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[10px] text-gray-500 uppercase", children: [
        "Depends on (",
        task.dependencies.length,
        ")"
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1 mt-1", children: task.dependencies.map((depId) => {
        const depNode = graph.get(depId);
        return /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => onNavigate(depId),
            className: `text-[10px] font-mono px-2 py-0.5 rounded border transition hover:bg-white/5 ${depNode?.task.status === "completed" ? "border-green-500/30 text-green-400" : "border-orange-500/30 text-orange-400"}`,
            children: [
              depId,
              " ",
              depNode ? depNode.task.status === "completed" ? "✓" : "⏳" : "?"
            ]
          },
          depId
        );
      }) })
    ] }),
    blocks.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mb-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-[10px] text-gray-500 uppercase", children: [
        "Blocks (",
        blocks.length,
        ")"
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1 mt-1", children: blocks.map((blockId) => /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: () => onNavigate(blockId),
          className: "text-[10px] font-mono px-2 py-0.5 rounded border border-gray-600 text-gray-400 hover:bg-white/5 transition",
          children: blockId
        },
        blockId
      )) })
    ] }),
    task.error_message && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: "w-3 h-3 inline mr-1" }),
      task.error_message
    ] })
  ] });
}
let msgCounter = 0;
const nextId = () => `vibe-${++msgCounter}-${Date.now()}`;
const useVibeStore = create((set, get) => ({
  connected: false,
  projectId: null,
  sessionId: null,
  messages: [],
  isStreaming: false,
  currentAgent: null,
  history: [],
  setConnected: (connected) => set({ connected }),
  setProjectId: (id2) => set({ projectId: id2 }),
  setSessionId: (id2) => set({ sessionId: id2 }),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setCurrentAgent: (agent) => set({ currentAgent: agent }),
  addUserMessage: (content) => set((state) => ({
    messages: [...state.messages, {
      id: nextId(),
      role: "user",
      content,
      timestamp: /* @__PURE__ */ new Date()
    }]
  })),
  appendAssistantText: (content) => set((state) => {
    const msgs = [...state.messages];
    const last = msgs[msgs.length - 1];
    if (last?.role === "assistant" && !last.files) {
      msgs[msgs.length - 1] = { ...last, content: last.content + content };
    } else {
      msgs.push({
        id: nextId(),
        role: "assistant",
        content,
        agent: state.currentAgent || void 0,
        toolUses: [],
        timestamp: /* @__PURE__ */ new Date()
      });
    }
    return { messages: msgs };
  }),
  addToolUse: (tool, file, status) => set((state) => {
    const msgs = [...state.messages];
    const last = msgs[msgs.length - 1];
    if (last?.role === "assistant") {
      const toolUses = [...last.toolUses || [], { tool, file, status }];
      msgs[msgs.length - 1] = { ...last, toolUses };
    }
    return { messages: msgs };
  }),
  completeMessage: (files, sessionId) => set((state) => {
    const msgs = [...state.messages];
    const last = msgs[msgs.length - 1];
    if (last?.role === "assistant") {
      msgs[msgs.length - 1] = { ...last, files };
    }
    return {
      messages: msgs,
      isStreaming: false,
      sessionId: sessionId || state.sessionId
    };
  }),
  addErrorMessage: (message) => set((state) => ({
    messages: [...state.messages, {
      id: nextId(),
      role: "system",
      content: `Error: ${message}`,
      timestamp: /* @__PURE__ */ new Date()
    }],
    isStreaming: false
  })),
  setHistory: (history) => set({ history }),
  clearMessages: () => set({ messages: [], sessionId: null, currentAgent: null })
}));
function createVibeSocket(projectId, onFrame, onClose) {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const ws2 = new WebSocket(`${wsBase}/api/v1/vibe/ws/${projectId}`);
  ws2.onmessage = (event) => {
    try {
      const frame = JSON.parse(event.data);
      onFrame(frame);
    } catch (e) {
      console.error("Failed to parse vibe frame:", e);
    }
  };
  ws2.onclose = () => onClose?.();
  ws2.onerror = (e) => console.error("Vibe WS error:", e);
  return ws2;
}
async function sendVibePrompt(ws2, prompt, outputDir, sessionId) {
  ws2.send(JSON.stringify({
    prompt,
    output_dir: outputDir,
    session_id: sessionId
  }));
}
function VibeChat({ projectId, outputDir }) {
  const [input, setInput] = reactExports.useState("");
  const wsRef = reactExports.useRef(null);
  const messagesEndRef = reactExports.useRef(null);
  const store = useVibeStore();
  reactExports.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [store.messages]);
  reactExports.useEffect(() => {
    const ws2 = createVibeSocket(
      projectId,
      (frame) => {
        switch (frame.type) {
          case "agent":
            store.setCurrentAgent(frame.name || null);
            break;
          case "text":
            store.appendAssistantText(frame.content || "");
            break;
          case "tool_use":
            store.addToolUse(frame.tool || "", frame.file || "", frame.status || "");
            break;
          case "error":
            store.addErrorMessage(frame.message || "Unknown error");
            break;
          case "complete":
            store.completeMessage(frame.files || [], frame.session_id || null);
            break;
        }
      },
      () => store.setConnected(false)
    );
    ws2.onopen = () => store.setConnected(true);
    wsRef.current = ws2;
    store.setProjectId(projectId);
    return () => {
      ws2.close();
      wsRef.current = null;
    };
  }, [projectId]);
  const handleSend = reactExports.useCallback(() => {
    if (!input.trim() || !wsRef.current || store.isStreaming) return;
    store.addUserMessage(input);
    store.setStreaming(true);
    sendVibePrompt(wsRef.current, input, outputDir, store.sessionId || void 0);
    setInput("");
  }, [input, outputDir, store.sessionId, store.isStreaming]);
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col h-full bg-gray-900 rounded-lg border border-gray-700", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 px-4 py-3 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Bot, { className: "w-5 h-5 text-purple-400" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm font-medium text-gray-200", children: "Vibe Coder" }),
      store.currentAgent && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "px-2 py-0.5 text-xs rounded-full bg-purple-900 text-purple-300", children: store.currentAgent }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "ml-auto flex items-center gap-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: `w-2 h-2 rounded-full ${store.connected ? "bg-green-400" : "bg-red-400"}` }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: store.connected ? "Connected" : "Disconnected" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-y-auto p-4 space-y-4", children: [
      store.messages.map((msg) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`, children: [
        msg.role !== "user" && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-7 h-7 rounded-full bg-purple-900 flex items-center justify-center flex-shrink-0", children: /* @__PURE__ */ jsxRuntimeExports.jsx(Bot, { className: "w-4 h-4 text-purple-300" }) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `max-w-[80%] ${msg.role === "user" ? "bg-blue-900 text-blue-100 rounded-2xl rounded-br-md px-4 py-2" : msg.role === "system" ? "bg-red-900/50 text-red-300 rounded-lg px-4 py-2" : "bg-gray-800 text-gray-200 rounded-2xl rounded-bl-md px-4 py-2"}`, children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-sm whitespace-pre-wrap", children: msg.content }),
          msg.toolUses && msg.toolUses.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mt-2 space-y-1", children: msg.toolUses.map((tu, i) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5 text-xs text-gray-400", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Wrench, { className: "w-3 h-3" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-purple-400", children: tu.tool }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "truncate", children: tu.file })
          ] }, i)) }),
          msg.files && msg.files.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mt-2 pt-2 border-t border-gray-700", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5 text-xs text-green-400", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-3 h-3" }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
              msg.files.length,
              " file",
              msg.files.length > 1 ? "s" : "",
              " changed"
            ] })
          ] }) })
        ] }),
        msg.role === "user" && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-7 h-7 rounded-full bg-blue-900 flex items-center justify-center flex-shrink-0", children: /* @__PURE__ */ jsxRuntimeExports.jsx(User, { className: "w-4 h-4 text-blue-300" }) })
      ] }, msg.id)),
      store.isStreaming && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-purple-400 text-sm", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
          store.currentAgent || "Agent",
          " is working..."
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { ref: messagesEndRef })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 py-3 border-t border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "textarea",
          {
            value: input,
            onChange: (e) => setInput(e.target.value),
            onKeyDown: handleKeyDown,
            placeholder: store.isStreaming ? "Agent is working..." : "Describe what to fix or change...",
            disabled: store.isStreaming || !store.connected,
            rows: 1,
            className: "flex-1 bg-gray-800 text-gray-200 rounded-lg px-4 py-2 text-sm resize-none\r\n                       border border-gray-600 focus:border-purple-500 focus:outline-none\r\n                       disabled:opacity-50 placeholder-gray-500"
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: handleSend,
            disabled: !input.trim() || store.isStreaming || !store.connected,
            className: "px-3 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700\r\n                       rounded-lg text-white transition-colors disabled:opacity-50",
            children: store.isStreaming ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Send, { className: "w-4 h-4" })
          }
        )
      ] }),
      store.sessionId && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-1 text-xs text-gray-600", children: [
        "Session: ",
        store.sessionId.slice(0, 8),
        "..."
      ] })
    ] })
  ] });
}
function GenerationMonitor() {
  const { generationProgress, agentActivity, logs, epics, runEpic, rerunEpic, generateAllTaskLists, loadEpics, currentProjectPath, wsConnected, taskProgress, epicTaskLists, selectedEpic } = useEngineStore();
  const { activeProjectId, getProject } = useProjectStore();
  const [activeTab, setActiveTab] = reactExports.useState("progress");
  const logsEndRef = reactExports.useRef(null);
  const activeProject = activeProjectId ? getProject(activeProjectId) : null;
  reactExports.useEffect(() => {
    console.log(`[Monitor] Tab switched to: ${activeTab}`);
    console.log(`[Monitor] State snapshot:`, {
      activeProjectId,
      activeProjectName: activeProject?.name || "none",
      activeProjectStatus: activeProject?.status || "none",
      wsConnected,
      generationProgress,
      agentCount: agentActivity.length,
      epicCount: epics.length,
      logCount: logs.length,
      currentProjectPath,
      taskProgress,
      selectedEpic
    });
  }, [activeTab]);
  reactExports.useEffect(() => {
    if (activeTab === "progress") {
      console.log(`[Monitor:Progress] progress=${generationProgress}% | project=${activeProject?.name || "none"} | status=${activeProject?.status || "idle"}`);
    }
  }, [activeTab, generationProgress, activeProject?.status]);
  reactExports.useEffect(() => {
    if (activeTab === "agents") {
      console.log(`[Monitor:Agents] ${agentActivity.length} agents active:`, agentActivity.slice(-5).map((a) => `${a.agent}:${a.status}`));
    }
  }, [activeTab, agentActivity.length]);
  reactExports.useEffect(() => {
    if (activeTab === "epics") {
      console.log(`[Monitor:Epics] ${epics.length} epics loaded:`, epics.map((e) => `${e.id}:${e.status}(${e.progress_percent}%)`));
    }
  }, [activeTab, epics.length]);
  reactExports.useEffect(() => {
    if (activeTab === "tasks") {
      const taskListKeys = Object.keys(epicTaskLists);
      const totalTasks = taskListKeys.reduce((sum, k2) => sum + (epicTaskLists[k2]?.tasks?.length || 0), 0);
      console.log(`[Monitor:Tasks] ${totalTasks} tasks across ${taskListKeys.length} epics | progress:`, taskProgress);
    }
  }, [activeTab, taskProgress, Object.keys(epicTaskLists).length]);
  reactExports.useEffect(() => {
    if (activeTab === "logs") {
      console.log(`[Monitor:Logs] ${logs.length} log entries (showing last 3):`, logs.slice(-3));
    }
  }, [activeTab, logs.length]);
  reactExports.useEffect(() => {
    if (activeProject) {
      const epicPath = activeProject.requirementsPath || activeProject.outputDir;
      const pathMatch = epicPath === currentProjectPath;
      console.log(`[Monitor] Project changed: ${activeProject.name}`);
      console.log(`[Monitor]   requirementsPath=${activeProject.requirementsPath || "(empty)"}`);
      console.log(`[Monitor]   outputDir=${activeProject.outputDir || "(empty)"}`);
      console.log(`[Monitor]   epicPath=${epicPath || "(empty)"}`);
      console.log(`[Monitor]   currentProjectPath=${currentProjectPath || "(empty)"}`);
      console.log(`[Monitor]   pathMatch=${pathMatch} | epicCount=${epics.length}`);
      const shouldLoad = epicPath && (!pathMatch || epics.length === 0);
      console.log(`[Monitor]   shouldLoad=${shouldLoad} (reason: ${!pathMatch ? "path changed" : epics.length === 0 ? "epics empty despite path match" : "already loaded"})`);
      if (shouldLoad) {
        console.log(`[Monitor] >>> Loading epics from: ${epicPath}`);
        loadEpics(epicPath);
      }
    } else {
      console.log(`[Monitor] No active project selected (activeProjectId=${activeProjectId})`);
    }
  }, [activeProject?.id, activeProject?.requirementsPath, activeProject?.outputDir, currentProjectPath, loadEpics]);
  reactExports.useEffect(() => {
    if (activeTab === "logs") {
      logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, activeTab]);
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-dark", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "progress",
          onClick: () => setActiveTab("progress"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Activity, { className: "w-4 h-4" }),
          label: "Progress"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "agents",
          onClick: () => setActiveTab("agents"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4" }),
          label: "Agents"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "epics",
          onClick: () => setActiveTab("epics"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Layers, { className: "w-4 h-4" }),
          label: `Epics${epics.length > 0 ? ` (${epics.length})` : ""}`
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "tasks",
          onClick: () => setActiveTab("tasks"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(ListChecks, { className: "w-4 h-4" }),
          label: "Tasks"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "deps",
          onClick: () => setActiveTab("deps"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-4 h-4" }),
          label: "Dependencies"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "logs",
          onClick: () => setActiveTab("logs"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Terminal, { className: "w-4 h-4" }),
          label: "Logs"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "enrichment",
          onClick: () => setActiveTab("enrichment"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(BookOpen, { className: "w-4 h-4" }),
          label: "Enrichment"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "llm-config",
          onClick: () => setActiveTab("llm-config"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Cpu, { className: "w-4 h-4" }),
          label: "LLM Config"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        TabButton,
        {
          active: activeTab === "vibe",
          onClick: () => setActiveTab("vibe"),
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Zap, { className: "w-4 h-4" }),
          label: "Vibe"
        }
      )
    ] }),
    activeTab === "vibe" ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
      VibeChat,
      {
        projectId: activeProject?.id || "default",
        outputDir: activeProject?.outputDir || "."
      }
    ) }) : activeTab === "llm-config" ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(LLMConfigEditor, {}) }) : activeTab === "enrichment" ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(EnrichmentView, {}) }) : activeTab === "deps" ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(TaskDependencyBoard, {}) }) : /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto p-4", children: [
      activeTab === "progress" && /* @__PURE__ */ jsxRuntimeExports.jsx(
        ProgressView,
        {
          progress: activeProject?.progress ?? generationProgress,
          status: activeProject?.status
        }
      ),
      activeTab === "agents" && /* @__PURE__ */ jsxRuntimeExports.jsx(AgentActivityView, { activity: agentActivity }),
      activeTab === "epics" && /* @__PURE__ */ jsxRuntimeExports.jsx(
        EpicSelector,
        {
          onRunEpic: runEpic,
          onRerunEpic: rerunEpic,
          onGenerateTaskList: generateAllTaskLists
        }
      ),
      activeTab === "tasks" && /* @__PURE__ */ jsxRuntimeExports.jsx(TaskList, {}),
      activeTab === "logs" && /* @__PURE__ */ jsxRuntimeExports.jsx(LogsView, { logs, logsEndRef })
    ] })
  ] });
}
function TabButton({ active, onClick, icon, label }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "button",
    {
      onClick,
      className: `flex items-center gap-2 px-4 py-2 text-sm font-medium transition ${active ? "text-engine-primary border-b-2 border-engine-primary" : "text-gray-400 hover:text-white"}`,
      children: [
        icon,
        label
      ]
    }
  );
}
function ProgressView({ progress, status }) {
  console.log(`[Monitor:Progress] Rendering: progress=${progress}% status=${status || "undefined"}`);
  const stages = [
    { name: "Analyzing Requirements", threshold: 10 },
    { name: "Generating Code", threshold: 40 },
    { name: "Running Validators", threshold: 60 },
    { name: "Building Project", threshold: 80 },
    { name: "Running Tests", threshold: 95 },
    { name: "Complete", threshold: 100 }
  ];
  const currentStage = stages.find((s) => progress < s.threshold) || stages[stages.length - 1];
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-6", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between text-sm mb-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400", children: "Overall Progress" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "font-mono", children: [
          progress,
          "%"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-3 bg-gray-700 rounded-full overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "h-full bg-gradient-to-r from-engine-primary to-engine-secondary transition-all duration-500",
          style: { width: `${progress}%` }
        }
      ) })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 p-4 bg-engine-darker rounded-lg", children: [
      status === "generating" ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-6 h-6 text-yellow-500 animate-spin" }) : progress === 100 ? /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-6 h-6 text-green-500" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-6 h-6 text-gray-500" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "font-medium", children: currentStage.name }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400", children: status === "generating" ? "In progress..." : status === "idle" ? "Waiting to start" : status })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2", children: stages.slice(0, -1).map((stage, index) => {
      const isComplete = progress >= stage.threshold;
      const isCurrent = currentStage === stage;
      return /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "div",
        {
          className: `flex items-center gap-3 p-2 rounded ${isCurrent ? "bg-engine-primary/10" : ""}`,
          children: [
            isComplete ? /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-4 h-4 text-green-500" }) : isCurrent ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 text-yellow-500 animate-spin" }) : /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-4 h-4 rounded-full border border-gray-600" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: isComplete ? "text-gray-300" : "text-gray-500", children: stage.name })
          ]
        },
        stage.name
      );
    }) })
  ] });
}
function AgentActivityView({ activity }) {
  if (activity.length === 0) {
    console.log("[Monitor:Agents] Empty state — no agent activity received via WebSocket");
    return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full flex items-center justify-center text-gray-500", children: /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "No agent activity yet. Start a generation to see agents." }) });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2", children: activity.map((item, index) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: "flex items-start gap-3 p-3 bg-engine-darker rounded-lg",
      children: [
        item.status === "running" ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 text-yellow-500 animate-spin mt-0.5" }) : item.status === "completed" ? /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-4 h-4 text-green-500 mt-0.5" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-4 h-4 text-red-500 mt-0.5" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium text-sm", children: item.agent }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: item.timestamp })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400 truncate", children: item.action })
        ] })
      ]
    },
    index
  )) });
}
function LogsView({ logs, logsEndRef }) {
  if (logs.length === 0) {
    console.log("[Monitor:Logs] Empty state — no logs received via WebSocket");
    return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full flex items-center justify-center text-gray-500", children: /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "No logs yet. Start a generation to see logs." }) });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "font-mono text-xs space-y-1", children: [
    logs.map((log, index) => /* @__PURE__ */ jsxRuntimeExports.jsx(
      "div",
      {
        className: `p-1 rounded ${log.includes("ERROR") || log.includes("FAILED") ? "bg-red-500/10 text-red-400" : log.includes("SUCCESS") || log.includes("PASSED") ? "bg-green-500/10 text-green-400" : log.includes("WARN") ? "bg-yellow-500/10 text-yellow-400" : "text-gray-400"}`,
        children: log
      },
      index
    )),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { ref: logsEndRef })
  ] });
}
const HEALTH_CHECK_INTERVAL = 2e3;
const MAX_HEALTH_CHECKS = 30;
function VNCViewer({ port, projectId, debugRecording, onDebugClick }) {
  const [status, setStatus] = reactExports.useState("checking");
  const [key, setKey] = reactExports.useState(0);
  const [healthCheckCount, setHealthCheckCount] = reactExports.useState(0);
  const [showIframe, setShowIframe] = reactExports.useState(false);
  const [containerLogs, setContainerLogs] = reactExports.useState("");
  const healthCheckRef = reactExports.useRef(null);
  const [clickMarkers, setClickMarkers] = reactExports.useState([]);
  const handleDebugOverlayClick = reactExports.useCallback((e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x2 = Math.round((e.clientX - rect.left) / rect.width * 100);
    const y2 = Math.round((e.clientY - rect.top) / rect.height * 100);
    const marker = { id: crypto.randomUUID(), x: x2, y: y2, fadeOut: false };
    setClickMarkers((prev) => [...prev, marker]);
    setTimeout(() => {
      setClickMarkers((prev) => prev.map((m2) => m2.id === marker.id ? { ...m2, fadeOut: true } : m2));
    }, 1500);
    setTimeout(() => {
      setClickMarkers((prev) => prev.filter((m2) => m2.id !== marker.id));
    }, 2e3);
    onDebugClick?.(x2, y2);
  }, [onDebugClick]);
  const vncUrl = `http://localhost:${port}/vnc.html?autoconnect=true&resize=scale&reconnect=true`;
  const checkVNCHealth = async () => {
    try {
      return new Promise((resolve) => {
        const img = new Image();
        const timeout = setTimeout(() => {
          img.onload = null;
          img.onerror = null;
          resolve(false);
        }, 2e3);
        img.onload = () => {
          clearTimeout(timeout);
          console.log(`[VNC] Health check passed - noVNC is serving on port ${port}`);
          resolve(true);
        };
        img.onerror = () => {
          clearTimeout(timeout);
          const favicon = new Image();
          const fallbackTimeout = setTimeout(() => {
            favicon.onload = null;
            favicon.onerror = null;
            resolve(false);
          }, 1e3);
          favicon.onload = () => {
            clearTimeout(fallbackTimeout);
            console.log(`[VNC] Fallback health check passed - port ${port}`);
            resolve(true);
          };
          favicon.onerror = () => {
            clearTimeout(fallbackTimeout);
            resolve(false);
          };
          favicon.src = `http://localhost:${port}/favicon.ico?t=${Date.now()}`;
        };
        img.src = `http://localhost:${port}/app/images/icons/novnc-16x16.png?t=${Date.now()}`;
      });
    } catch (error) {
      console.error("[VNC] Health check error:", error);
      return false;
    }
  };
  reactExports.useEffect(() => {
    let isMounted = true;
    setStatus("checking");
    setHealthCheckCount(0);
    setShowIframe(false);
    const runHealthCheck = async () => {
      let attempts = 0;
      while (attempts < MAX_HEALTH_CHECKS && isMounted) {
        const isHealthy = await checkVNCHealth();
        if (!isMounted) break;
        attempts++;
        setHealthCheckCount(attempts);
        if (isHealthy) {
          console.log(`[VNC] Port ${port} is ready after ${attempts} checks`);
          setStatus("loading");
          setShowIframe(true);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, HEALTH_CHECK_INTERVAL));
      }
      if (isMounted) {
        console.error(`[VNC] Port ${port} not available after ${MAX_HEALTH_CHECKS} attempts`);
        setStatus("error");
      }
    };
    runHealthCheck();
    return () => {
      isMounted = false;
      if (healthCheckRef.current) {
        clearTimeout(healthCheckRef.current);
      }
    };
  }, [port, key]);
  reactExports.useEffect(() => {
    if (status === "error" && window.electronAPI?.getProjectLogs) {
      window.electronAPI.getProjectLogs(projectId, 50).then((logs) => {
        setContainerLogs(logs);
        console.log("[VNC] Container logs fetched for debugging");
      }).catch((err) => {
        console.warn("[VNC] Could not fetch container logs:", err);
      });
    }
  }, [status, projectId]);
  const handleLoad = () => {
    console.log("[VNC] iframe loaded successfully:", vncUrl);
    setStatus("loaded");
  };
  const handleError = (e) => {
    console.error("[VNC] iframe error:", vncUrl, e);
    if (status !== "checking") {
      setStatus("error");
    }
  };
  const handleReconnect = () => {
    setStatus("checking");
    setShowIframe(false);
    setKey((k2) => k2 + 1);
  };
  const openInBrowser = () => {
    window.open(vncUrl, "_blank");
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative w-full h-full bg-black", children: [
    showIframe && /* @__PURE__ */ jsxRuntimeExports.jsx(
      "iframe",
      {
        src: vncUrl,
        className: "w-full h-full border-0",
        title: `VNC Preview - ${projectId}`,
        sandbox: "allow-scripts allow-same-origin allow-forms allow-modals allow-popups",
        allow: "clipboard-read; clipboard-write",
        onLoad: handleLoad,
        onError: handleError,
        style: { display: status === "loaded" ? "block" : "none" }
      },
      key
    ),
    status === "checking" && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute inset-0 flex items-center justify-center bg-black", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-10 h-10 mx-auto mb-3 text-yellow-500 animate-pulse" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-300", children: "Waiting for VNC server..." }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 mt-1", children: [
        "Port ",
        port,
        " • Check ",
        healthCheckCount,
        "/",
        MAX_HEALTH_CHECKS
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-48 h-1 bg-gray-700 rounded mt-3 mx-auto overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
        "div",
        {
          className: "h-full bg-yellow-500 transition-all duration-500",
          style: { width: `${healthCheckCount / MAX_HEALTH_CHECKS * 100}%` }
        }
      ) })
    ] }) }),
    status === "loading" && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute inset-0 flex items-center justify-center bg-black", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(RefreshCw, { className: "w-10 h-10 mx-auto mb-3 text-engine-primary animate-spin" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-300", children: "Connecting to VNC..." }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 mt-1", children: [
        "Port ",
        port
      ] })
    ] }) }),
    status === "error" && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute inset-0 flex items-center justify-center bg-black overflow-auto py-4", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center max-w-lg", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(AlertCircle, { className: "w-10 h-10 mx-auto mb-3 text-red-500" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-300", children: "Failed to connect to VNC" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 mt-1", children: [
        "Port ",
        port,
        " - Container may still be starting"
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2 mt-4 justify-center", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: handleReconnect,
            className: "px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition",
            children: "Retry"
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: openInBrowser,
            className: "px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition flex items-center gap-2",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-4 h-4" }),
              "Open in Browser"
            ]
          }
        )
      ] }),
      containerLogs && /* @__PURE__ */ jsxRuntimeExports.jsxs("details", { className: "mt-4 text-left", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("summary", { className: "text-xs text-gray-400 cursor-pointer hover:text-gray-300", children: "Container Logs (click to expand)" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("pre", { className: "mt-2 p-2 bg-gray-900 text-xs text-gray-400 overflow-auto max-h-40 rounded text-left whitespace-pre-wrap", children: containerLogs })
      ] })
    ] }) }),
    status === "loaded" && !debugRecording && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "absolute top-2 right-2 flex items-center gap-2 px-2 py-1 bg-black/50 rounded text-xs", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-2 h-2 rounded-full bg-green-500 animate-pulse" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300", children: "Live" })
    ] }),
    debugRecording && status === "loaded" && /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "div",
      {
        className: "absolute inset-0 cursor-crosshair",
        style: { zIndex: 10 },
        onClick: handleDebugOverlayClick,
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "absolute top-2 left-2 flex items-center gap-2 px-2 py-1 bg-red-600/80 rounded text-xs z-20", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-2 h-2 rounded-full bg-red-400 animate-pulse" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-white font-medium", children: "REC" })
          ] }),
          clickMarkers.map((marker) => /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: `absolute w-6 h-6 -ml-3 -mt-3 rounded-full border-2 border-red-400 bg-red-500/30 transition-opacity duration-500 ${marker.fadeOut ? "opacity-0" : "opacity-100"}`,
              style: { left: `${marker.x}%`, top: `${marker.y}%` },
              children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute inset-0 rounded-full bg-red-400/50 animate-ping" })
            },
            marker.id
          ))
        ]
      }
    )
  ] });
}
function LivePreview() {
  const { previewProjectId, getProject, setPreviewProject } = useProjectStore();
  const [isFullscreen, setIsFullscreen] = reactExports.useState(false);
  const project = previewProjectId ? getProject(previewProjectId) : null;
  if (!project) {
    return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full flex items-center justify-center text-gray-500", children: /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "No preview selected" }) });
  }
  const openInBrowser = () => {
    if (project.appPort) {
      window.open(`http://localhost:${project.appPort}`, "_blank");
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: `flex flex-col bg-engine-dark ${isFullscreen ? "fixed inset-0 z-50" : "h-full"}`,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between p-3 border-b border-gray-700", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-3 h-3 rounded-full bg-green-500 animate-pulse" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm font-medium", children: project.name }),
            project.vncPort && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
              "VNC:",
              project.vncPort
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
            project.appPort && /* @__PURE__ */ jsxRuntimeExports.jsx(
              "button",
              {
                onClick: openInBrowser,
                className: "p-1.5 hover:bg-gray-700 rounded transition",
                title: "Open in Browser",
                children: /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-4 h-4" })
              }
            ),
            /* @__PURE__ */ jsxRuntimeExports.jsx(
              "button",
              {
                onClick: () => setIsFullscreen(!isFullscreen),
                className: "p-1.5 hover:bg-gray-700 rounded transition",
                title: isFullscreen ? "Exit Fullscreen" : "Fullscreen",
                children: isFullscreen ? /* @__PURE__ */ jsxRuntimeExports.jsx(Minimize2, { className: "w-4 h-4" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Maximize2, { className: "w-4 h-4" })
              }
            ),
            /* @__PURE__ */ jsxRuntimeExports.jsx(
              "button",
              {
                onClick: () => setPreviewProject(null),
                className: "p-1.5 hover:bg-gray-700 rounded transition",
                title: "Close Preview",
                children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-4 h-4" })
              }
            )
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 bg-black", children: project.vncPort ? /* @__PURE__ */ jsxRuntimeExports.jsx(VNCViewer, { port: project.vncPort, projectId: project.id }) : /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-full flex items-center justify-center text-gray-500", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(RefreshCw, { className: "w-8 h-8 mx-auto mb-2 animate-spin" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "Waiting for VNC connection..." }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs mt-1", children: "Container is starting" })
        ] }) }) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between px-3 py-1.5 border-t border-gray-700 text-xs text-gray-500", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            "Status: ",
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-green-400", children: project.status })
          ] }),
          project.appPort && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            "App: ",
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-blue-400", children: [
              "localhost:",
              project.appPort
            ] })
          ] })
        ] })
      ]
    }
  );
}
function getPortalAPIBase() {
  if (typeof window !== "undefined" && window.location.protocol === "file:") {
    return "http://localhost:8000/api/v1/portal";
  }
  return "/api/v1/portal";
}
const PORTAL_API_BASE = getPortalAPIBase();
async function fetchJSON(url, options) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    }
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`HTTP ${response.status}: ${errorText}`);
  }
  return response.json();
}
async function fetchWithFiles(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`HTTP ${response.status}: ${errorText}`);
  }
  return response.json();
}
const cellAPI = {
  /**
   * Search marketplace cells
   */
  search: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.query) params.set("query", filters.query);
    if (filters.category) params.set("category", filters.category);
    if (filters.tags?.length) params.set("tags", filters.tags.join(","));
    if (filters.techStack?.length) params.set("tech_stack", filters.techStack.join(","));
    if (filters.author) params.set("author", filters.author);
    if (filters.visibility) params.set("visibility", filters.visibility);
    if (filters.status) params.set("status", filters.status);
    if (filters.minRating) params.set("min_rating", String(filters.minRating));
    if (filters.sortBy) params.set("sort_by", filters.sortBy);
    if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
    if (filters.page) params.set("page", String(filters.page));
    if (filters.pageSize) params.set("page_size", String(filters.pageSize));
    return fetchJSON(
      `${PORTAL_API_BASE}/marketplace/search?${params.toString()}`
    );
  },
  /**
   * Get cell by ID
   */
  getById: async (cellId) => {
    return fetchJSON(`${PORTAL_API_BASE}/cells/${cellId}`);
  },
  /**
   * Get cell by namespace (e.g., "author/cell-name")
   */
  getByNamespace: async (namespace) => {
    return fetchJSON(`${PORTAL_API_BASE}/cells/ns/${namespace}`);
  },
  /**
   * Install a cell from marketplace into a colony
   */
  install: async (request) => {
    return fetchJSON(`${PORTAL_API_BASE}/cells/${request.cellId}/install`, {
      method: "POST",
      body: JSON.stringify({
        version: request.version,
        target_namespace: request.targetNamespace
      })
    });
  },
  /**
   * Get trending cells
   */
  getTrending: async (limit = 10) => {
    const result = await fetchJSON(
      `${PORTAL_API_BASE}/marketplace/search?sort_by=downloads&page_size=${limit}`
    );
    return result.cells;
  },
  /**
   * Get recently published cells
   */
  getRecent: async (limit = 10) => {
    const result = await fetchJSON(
      `${PORTAL_API_BASE}/marketplace/search?sort_by=recent&page_size=${limit}`
    );
    return result.cells;
  },
  /**
   * Get top rated cells
   */
  getTopRated: async (limit = 10) => {
    const result = await fetchJSON(
      `${PORTAL_API_BASE}/marketplace/search?sort_by=rating&page_size=${limit}`
    );
    return result.cells;
  },
  /**
   * Get cells by category
   */
  getByCategory: async (category, limit = 20) => {
    const result = await fetchJSON(
      `${PORTAL_API_BASE}/marketplace/search?category=${category}&page_size=${limit}`
    );
    return result.cells;
  }
};
const publicationAPI = {
  /**
   * Publish a new cell to the marketplace
   */
  publishCell: async (request, tenantId) => {
    const formData = new FormData();
    formData.append("name", request.name);
    formData.append("display_name", request.displayName);
    formData.append("description", request.description);
    if (request.longDescription) {
      formData.append("long_description", request.longDescription);
    }
    formData.append("category", request.category);
    formData.append("tags", JSON.stringify(request.tags));
    formData.append("tech_stack", JSON.stringify(request.techStack));
    formData.append("license", request.license);
    formData.append("visibility", request.visibility);
    if (request.repositoryUrl) {
      formData.append("repository_url", request.repositoryUrl);
    }
    if (request.documentationUrl) {
      formData.append("documentation_url", request.documentationUrl);
    }
    if (request.iconFile) {
      formData.append("icon", request.iconFile);
    }
    if (request.screenshotFiles) {
      request.screenshotFiles.forEach((file, index) => {
        formData.append(`screenshot_${index}`, file);
      });
    }
    return fetchWithFiles(
      `${PORTAL_API_BASE}/cells?tenant_id=${tenantId}`,
      formData
    );
  },
  /**
   * Upload a new version of a cell
   */
  uploadVersion: async (cellId, request) => {
    const formData = new FormData();
    formData.append("version", request.version);
    formData.append("changelog", request.changelog);
    formData.append("artifact", request.artifactFile);
    return fetchWithFiles(`${PORTAL_API_BASE}/cells/${cellId}/versions`, formData);
  },
  /**
   * Update cell metadata
   */
  updateCell: async (cellId, updates) => {
    return fetchJSON(`${PORTAL_API_BASE}/cells/${cellId}`, {
      method: "PATCH",
      body: JSON.stringify(updates)
    });
  },
  /**
   * Delete a cell (owner only)
   */
  deleteCell: async (cellId) => {
    return fetchJSON(`${PORTAL_API_BASE}/cells/${cellId}`, {
      method: "DELETE"
    });
  }
};
const tenantAPI = {
  /**
   * Get all tenants for current user
   */
  getMyTenants: async () => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants`);
  },
  /**
   * Get tenant by ID
   */
  getById: async (tenantId) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}`);
  },
  /**
   * Create a new tenant
   */
  create: async (data) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants`, {
      method: "POST",
      body: JSON.stringify(data)
    });
  },
  /**
   * Update tenant
   */
  update: async (tenantId, updates) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}`, {
      method: "PATCH",
      body: JSON.stringify(updates)
    });
  },
  /**
   * Get tenant members
   */
  getMembers: async (tenantId) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}/members`);
  },
  /**
   * Invite a member
   */
  inviteMember: async (tenantId, email, role) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}/invites`, {
      method: "POST",
      body: JSON.stringify({ email, role })
    });
  },
  /**
   * Update member role
   */
  updateMemberRole: async (tenantId, memberId, role) => {
    return fetchJSON(
      `${PORTAL_API_BASE}/tenants/${tenantId}/members/${memberId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ role })
      }
    );
  },
  /**
   * Remove a member
   */
  removeMember: async (tenantId, memberId) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}/members/${memberId}`, {
      method: "DELETE"
    });
  },
  /**
   * Get cells owned by tenant
   */
  getCells: async (tenantId) => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}/cells`);
  }
};
const reviewAPI = {
  /**
   * Get reviews for a cell
   */
  getForCell: async (cellId, filters = {}) => {
    const params = new URLSearchParams();
    params.set("cell_id", cellId);
    if (filters.rating) params.set("rating", String(filters.rating));
    if (filters.verified !== void 0) params.set("verified", String(filters.verified));
    if (filters.sortBy) params.set("sort_by", filters.sortBy);
    if (filters.page) params.set("page", String(filters.page));
    if (filters.pageSize) params.set("page_size", String(filters.pageSize));
    return fetchJSON(`${PORTAL_API_BASE}/reviews?${params.toString()}`);
  },
  /**
   * Get review stats for a cell
   */
  getStats: async (cellId) => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/stats/${cellId}`);
  },
  /**
   * Submit a review
   */
  submit: async (cellId, data) => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews`, {
      method: "POST",
      body: JSON.stringify({ cell_id: cellId, ...data })
    });
  },
  /**
   * Update a review
   */
  update: async (reviewId, data) => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/${reviewId}`, {
      method: "PATCH",
      body: JSON.stringify(data)
    });
  },
  /**
   * Delete a review
   */
  delete: async (reviewId) => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/${reviewId}`, {
      method: "DELETE"
    });
  },
  /**
   * Vote on a review (helpful/not helpful)
   */
  vote: async (reviewId, vote) => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/${reviewId}/vote`, {
      method: "POST",
      body: JSON.stringify({ vote })
    });
  },
  /**
   * Author response to a review
   */
  respond: async (reviewId, content) => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/${reviewId}/respond`, {
      method: "POST",
      body: JSON.stringify({ content })
    });
  }
};
const categoryAPI = {
  /**
   * Get all categories
   */
  getAll: async () => {
    return fetchJSON(`${PORTAL_API_BASE}/categories`);
  },
  /**
   * Get category by ID
   */
  getById: async (categoryId) => {
    return fetchJSON(`${PORTAL_API_BASE}/categories/${categoryId}`);
  }
};
const usePortalStore = create()((set, get) => ({
  // Initial state
  searchQuery: "",
  searchFilters: {},
  searchResults: [],
  totalResults: 0,
  currentPage: 1,
  pageSize: 20,
  hasMore: false,
  isSearching: false,
  searchError: null,
  trendingCells: [],
  recentCells: [],
  topRatedCells: [],
  featuredLoading: false,
  categories: [],
  categoriesLoading: false,
  selectedCell: null,
  selectedCellReviews: [],
  selectedCellReviewStats: null,
  cellDetailLoading: false,
  // Actions
  setSearchQuery: (query) => {
    set({ searchQuery: query });
  },
  setSearchFilters: (filters) => {
    set((state) => ({
      searchFilters: { ...state.searchFilters, ...filters }
    }));
  },
  search: async () => {
    const { searchQuery, searchFilters, pageSize } = get();
    set({
      isSearching: true,
      searchError: null,
      currentPage: 1
    });
    try {
      const result = await cellAPI.search({
        ...searchFilters,
        query: searchQuery || void 0,
        page: 1,
        pageSize
      });
      set({
        searchResults: result.cells,
        totalResults: result.total,
        hasMore: result.hasMore,
        currentPage: result.page,
        isSearching: false
      });
    } catch (error) {
      set({
        searchError: error.message || "Search failed",
        isSearching: false
      });
    }
  },
  searchNextPage: async () => {
    const { searchQuery, searchFilters, currentPage, pageSize, hasMore, isSearching } = get();
    if (!hasMore || isSearching) return;
    set({ isSearching: true });
    try {
      const result = await cellAPI.search({
        ...searchFilters,
        query: searchQuery || void 0,
        page: currentPage + 1,
        pageSize
      });
      set((state) => ({
        searchResults: [...state.searchResults, ...result.cells],
        totalResults: result.total,
        hasMore: result.hasMore,
        currentPage: result.page,
        isSearching: false
      }));
    } catch (error) {
      set({
        searchError: error.message || "Failed to load more",
        isSearching: false
      });
    }
  },
  clearSearch: () => {
    set({
      searchQuery: "",
      searchFilters: {},
      searchResults: [],
      totalResults: 0,
      currentPage: 1,
      hasMore: false,
      searchError: null
    });
  },
  loadFeaturedCells: async () => {
    set({ featuredLoading: true });
    try {
      const [trending, recent, topRated] = await Promise.all([
        cellAPI.getTrending(8),
        cellAPI.getRecent(8),
        cellAPI.getTopRated(8)
      ]);
      set({
        trendingCells: trending,
        recentCells: recent,
        topRatedCells: topRated,
        featuredLoading: false
      });
    } catch (error) {
      console.error("Failed to load featured cells:", error);
      set({ featuredLoading: false });
    }
  },
  loadCategories: async () => {
    set({ categoriesLoading: true });
    try {
      const categories = await categoryAPI.getAll();
      set({
        categories,
        categoriesLoading: false
      });
    } catch (error) {
      console.error("Failed to load categories:", error);
      set({ categoriesLoading: false });
    }
  },
  selectCell: (cell) => {
    set({
      selectedCell: cell,
      selectedCellReviews: [],
      selectedCellReviewStats: null
    });
  },
  loadCellDetail: async (cellId) => {
    set({ cellDetailLoading: true });
    try {
      const [cell, reviewData] = await Promise.all([
        cellAPI.getById(cellId),
        reviewAPI.getForCell(cellId, { pageSize: 10 })
      ]);
      set({
        selectedCell: cell,
        selectedCellReviews: reviewData.reviews,
        selectedCellReviewStats: reviewData.stats,
        cellDetailLoading: false
      });
    } catch (error) {
      console.error("Failed to load cell detail:", error);
      set({ cellDetailLoading: false });
    }
  },
  loadCellReviews: async (cellId, page = 1) => {
    try {
      const reviewData = await reviewAPI.getForCell(cellId, { page, pageSize: 10 });
      set((state) => ({
        selectedCellReviews: page === 1 ? reviewData.reviews : [...state.selectedCellReviews, ...reviewData.reviews],
        selectedCellReviewStats: reviewData.stats
      }));
    } catch (error) {
      console.error("Failed to load reviews:", error);
    }
  },
  installCell: async (cellId, version, targetNamespace = "default") => {
    try {
      const result = await cellAPI.install({
        cellId,
        version,
        targetNamespace
      });
      if (result.success) {
        const cell = get().selectedCell;
        if (cell?.id === cellId) {
          const updated = await cellAPI.getById(cellId);
          set({ selectedCell: updated });
        }
      }
      return result;
    } catch (error) {
      return { success: false, error: error.message || "Install failed" };
    }
  }
}));
const useTenantStore = create()(
  persist(
    (set, get) => ({
      // Initial state
      tenants: [],
      activeTenantId: null,
      isLoading: false,
      error: null,
      activeTenantMembers: [],
      activeTenantCells: [],
      detailsLoading: false,
      // Computed
      getActiveTenant: () => {
        const { tenants, activeTenantId } = get();
        return tenants.find((t2) => t2.id === activeTenantId) || null;
      },
      getMyRole: () => {
        const { activeTenantMembers } = get();
        return activeTenantMembers[0]?.role || null;
      },
      // Actions
      loadTenants: async () => {
        set({ isLoading: true, error: null });
        try {
          const tenants = await tenantAPI.getMyTenants();
          const { activeTenantId } = get();
          set({
            tenants,
            isLoading: false,
            // Auto-select first tenant if none selected
            activeTenantId: activeTenantId && tenants.find((t2) => t2.id === activeTenantId) ? activeTenantId : tenants[0]?.id || null
          });
          if (get().activeTenantId) {
            get().loadTenantDetails();
          }
        } catch (error) {
          set({
            error: error.message || "Failed to load tenants",
            isLoading: false
          });
        }
      },
      switchTenant: (tenantId) => {
        const { tenants } = get();
        if (tenants.find((t2) => t2.id === tenantId)) {
          set({
            activeTenantId: tenantId,
            activeTenantMembers: [],
            activeTenantCells: []
          });
          get().loadTenantDetails();
        }
      },
      createTenant: async (data) => {
        set({ isLoading: true, error: null });
        try {
          const tenant = await tenantAPI.create(data);
          set((state) => ({
            tenants: [...state.tenants, tenant],
            activeTenantId: tenant.id,
            isLoading: false
          }));
          return tenant;
        } catch (error) {
          set({
            error: error.message || "Failed to create tenant",
            isLoading: false
          });
          return null;
        }
      },
      updateTenant: async (tenantId, updates) => {
        try {
          const updated = await tenantAPI.update(tenantId, updates);
          set((state) => ({
            tenants: state.tenants.map((t2) => t2.id === tenantId ? updated : t2)
          }));
          return true;
        } catch (error) {
          set({ error: error.message || "Failed to update tenant" });
          return false;
        }
      },
      loadTenantDetails: async () => {
        const { activeTenantId } = get();
        if (!activeTenantId) return;
        set({ detailsLoading: true });
        try {
          const [members, cells] = await Promise.all([
            tenantAPI.getMembers(activeTenantId),
            tenantAPI.getCells(activeTenantId)
          ]);
          set({
            activeTenantMembers: members,
            activeTenantCells: cells,
            detailsLoading: false
          });
        } catch (error) {
          console.error("Failed to load tenant details:", error);
          set({ detailsLoading: false });
        }
      },
      inviteMember: async (email, role) => {
        const { activeTenantId } = get();
        if (!activeTenantId) return false;
        try {
          await tenantAPI.inviteMember(activeTenantId, email, role);
          return true;
        } catch (error) {
          set({ error: error.message || "Failed to invite member" });
          return false;
        }
      },
      updateMemberRole: async (memberId, role) => {
        const { activeTenantId } = get();
        if (!activeTenantId) return false;
        try {
          const updated = await tenantAPI.updateMemberRole(activeTenantId, memberId, role);
          set((state) => ({
            activeTenantMembers: state.activeTenantMembers.map(
              (m2) => m2.id === memberId ? updated : m2
            )
          }));
          return true;
        } catch (error) {
          set({ error: error.message || "Failed to update role" });
          return false;
        }
      },
      removeMember: async (memberId) => {
        const { activeTenantId } = get();
        if (!activeTenantId) return false;
        try {
          await tenantAPI.removeMember(activeTenantId, memberId);
          set((state) => ({
            activeTenantMembers: state.activeTenantMembers.filter((m2) => m2.id !== memberId)
          }));
          return true;
        } catch (error) {
          set({ error: error.message || "Failed to remove member" });
          return false;
        }
      }
    }),
    {
      name: "coding-engine-tenants",
      partialize: (state) => ({
        activeTenantId: state.activeTenantId
      })
    }
  )
);
function SearchBar({
  value,
  onChange,
  onSearch,
  placeholder = "Search cells...",
  debounceMs = 300,
  autoFocus = false,
  className = ""
}) {
  const [localValue, setLocalValue] = reactExports.useState(value);
  const debounceRef = reactExports.useRef(null);
  const inputRef = reactExports.useRef(null);
  reactExports.useEffect(() => {
    setLocalValue(value);
  }, [value]);
  reactExports.useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      if (localValue !== value) {
        onChange(localValue);
      }
    }, debounceMs);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [localValue, debounceMs, onChange, value]);
  reactExports.useEffect(() => {
    if (autoFocus && inputRef.current) {
      inputRef.current.focus();
    }
  }, [autoFocus]);
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && onSearch) {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      onChange(localValue);
      onSearch();
    }
  };
  const handleClear = () => {
    setLocalValue("");
    onChange("");
    inputRef.current?.focus();
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `relative ${className}`, children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none", children: /* @__PURE__ */ jsxRuntimeExports.jsx(Search, { className: "w-4 h-4 text-gray-500" }) }),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      "input",
      {
        ref: inputRef,
        type: "text",
        value: localValue,
        onChange: (e) => setLocalValue(e.target.value),
        onKeyDown: handleKeyDown,
        placeholder,
        className: "\r\n          w-full\r\n          pl-10 pr-10 py-2\r\n          bg-engine-darker\r\n          border border-gray-600\r\n          rounded-lg\r\n          text-white\r\n          placeholder-gray-500\r\n          focus:outline-none\r\n          focus:border-engine-primary\r\n          focus:ring-1\r\n          focus:ring-engine-primary\r\n          transition-colors\r\n        "
      }
    ),
    localValue && /* @__PURE__ */ jsxRuntimeExports.jsx(
      "button",
      {
        type: "button",
        onClick: handleClear,
        className: "\r\n            absolute inset-y-0 right-0 pr-3\r\n            flex items-center\r\n            text-gray-500\r\n            hover:text-gray-300\r\n            transition-colors\r\n          ",
        "aria-label": "Clear search",
        children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-4 h-4" })
      }
    )
  ] });
}
const sizeClasses = {
  sm: "w-3 h-3",
  md: "w-4 h-4",
  lg: "w-5 h-5"
};
function StarRating({
  rating,
  maxRating = 5,
  size = "md",
  interactive = false,
  onChange,
  showValue = false,
  className = ""
}) {
  const handleClick = (value) => {
    if (interactive && onChange) {
      onChange(value);
    }
  };
  const handleKeyDown = (e, value) => {
    if (interactive && onChange && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      onChange(value);
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `flex items-center gap-0.5 ${className}`, children: [
    Array.from({ length: maxRating }, (_, i) => {
      const value = i + 1;
      const filled = value <= rating;
      const halfFilled = !filled && value - 0.5 <= rating;
      return /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          type: "button",
          disabled: !interactive,
          onClick: () => handleClick(value),
          onKeyDown: (e) => handleKeyDown(e, value),
          className: `
              relative
              ${interactive ? "cursor-pointer hover:scale-110 transition-transform" : "cursor-default"}
              ${interactive ? "focus:outline-none focus:ring-2 focus:ring-engine-primary focus:ring-offset-1 focus:ring-offset-engine-dark rounded" : ""}
            `,
          "aria-label": interactive ? `Rate ${value} out of ${maxRating}` : void 0,
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(
              Star,
              {
                className: `${sizeClasses[size]} text-gray-600`,
                fill: "none",
                strokeWidth: 1.5
              }
            ),
            (filled || halfFilled) && /* @__PURE__ */ jsxRuntimeExports.jsx(
              Star,
              {
                className: `
                  ${sizeClasses[size]}
                  text-yellow-400
                  absolute top-0 left-0
                  ${halfFilled ? "clip-path-half" : ""}
                `,
                fill: "currentColor",
                strokeWidth: 1.5,
                style: halfFilled ? { clipPath: "inset(0 50% 0 0)" } : void 0
              }
            )
          ]
        },
        i
      );
    }),
    showValue && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "ml-1.5 text-sm text-gray-400", children: rating.toFixed(1) })
  ] });
}
function RatingDisplay({
  rating,
  reviewCount,
  size = "sm",
  className = ""
}) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `flex items-center gap-1.5 ${className}`, children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx(StarRating, { rating, size }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-sm text-gray-400", children: [
      rating.toFixed(1),
      " (",
      reviewCount.toLocaleString(),
      ")"
    ] })
  ] });
}
const SORT_OPTIONS = [
  { value: "relevance", label: "Relevance" },
  { value: "downloads", label: "Most Downloads" },
  { value: "rating", label: "Highest Rated" },
  { value: "recent", label: "Recently Added" },
  { value: "name", label: "Name (A-Z)" }
];
const TECH_STACKS = [
  "React",
  "Vue",
  "Angular",
  "Node.js",
  "Python",
  "TypeScript",
  "Go",
  "Rust",
  "Java",
  "Docker",
  "Kubernetes",
  "PostgreSQL",
  "MongoDB",
  "Redis",
  "GraphQL"
];
function FilterPanel({
  categories,
  filters,
  onFiltersChange,
  onClear,
  className = ""
}) {
  const [expandedSections, setExpandedSections] = reactExports.useState(
    /* @__PURE__ */ new Set(["category", "sort"])
  );
  const toggleSection = (section) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };
  const activeFilterCount = [
    filters.category,
    filters.minRating,
    filters.techStack?.length,
    filters.tags?.length
  ].filter(Boolean).length;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `bg-engine-dark rounded-lg border border-gray-700 ${className}`, children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between p-4 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Filter, { className: "w-4 h-4 text-gray-400" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium", children: "Filters" }),
        activeFilterCount > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "px-1.5 py-0.5 bg-engine-primary rounded text-xs", children: activeFilterCount })
      ] }),
      activeFilterCount > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: onClear,
          className: "text-xs text-gray-400 hover:text-white transition-colors",
          children: "Clear all"
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      FilterSection,
      {
        title: "Sort By",
        isExpanded: expandedSections.has("sort"),
        onToggle: () => toggleSection("sort"),
        children: /* @__PURE__ */ jsxRuntimeExports.jsx(
          "select",
          {
            value: filters.sortBy || "relevance",
            onChange: (e) => onFiltersChange({ sortBy: e.target.value }),
            className: "\r\n            w-full\r\n            px-3 py-2\r\n            bg-engine-darker\r\n            border border-gray-600\r\n            rounded\r\n            text-sm\r\n            focus:outline-none\r\n            focus:border-engine-primary\r\n          ",
            children: SORT_OPTIONS.map((option) => /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: option.value, children: option.label }, option.value))
          }
        )
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      FilterSection,
      {
        title: "Category",
        isExpanded: expandedSections.has("category"),
        onToggle: () => toggleSection("category"),
        children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: () => onFiltersChange({ category: void 0 }),
              className: `
              w-full text-left px-2 py-1.5 rounded text-sm
              ${!filters.category ? "bg-engine-primary/20 text-engine-primary" : "text-gray-400 hover:text-white hover:bg-gray-700"}
              transition-colors
            `,
              children: "All Categories"
            }
          ),
          categories.map((category) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
            "button",
            {
              onClick: () => onFiltersChange({ category: category.id }),
              className: `
                w-full text-left px-2 py-1.5 rounded text-sm flex items-center justify-between
                ${filters.category === category.id ? "bg-engine-primary/20 text-engine-primary" : "text-gray-400 hover:text-white hover:bg-gray-700"}
                transition-colors
              `,
              children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: category.displayName }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: category.cellCount })
              ]
            },
            category.id
          ))
        ] })
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      FilterSection,
      {
        title: "Minimum Rating",
        isExpanded: expandedSections.has("rating"),
        onToggle: () => toggleSection("rating"),
        children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-2", children: [4, 3, 2, 1].map((rating) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => onFiltersChange({
              minRating: filters.minRating === rating ? void 0 : rating
            }),
            className: `
                w-full flex items-center gap-2 px-2 py-1.5 rounded
                ${filters.minRating === rating ? "bg-engine-primary/20" : "hover:bg-gray-700"}
                transition-colors
              `,
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(StarRating, { rating, size: "sm" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-400", children: "& up" })
            ]
          },
          rating
        )) })
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      FilterSection,
      {
        title: "Tech Stack",
        isExpanded: expandedSections.has("tech"),
        onToggle: () => toggleSection("tech"),
        children: /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5", children: TECH_STACKS.map((tech) => {
          const isSelected = filters.techStack?.includes(tech);
          return /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: () => {
                const current = filters.techStack || [];
                const updated = isSelected ? current.filter((t2) => t2 !== tech) : [...current, tech];
                onFiltersChange({ techStack: updated.length ? updated : void 0 });
              },
              className: `
                  px-2 py-1 rounded text-xs
                  ${isSelected ? "bg-engine-primary text-white" : "bg-engine-darker text-gray-400 hover:bg-gray-700"}
                  transition-colors
                `,
              children: tech
            },
            tech
          );
        }) })
      }
    ),
    activeFilterCount > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 border-t border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-xs text-gray-500 mb-2", children: "Active Filters" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-wrap gap-1.5", children: [
        filters.category && /* @__PURE__ */ jsxRuntimeExports.jsx(
          FilterTag,
          {
            label: categories.find((c) => c.id === filters.category)?.displayName || filters.category,
            onRemove: () => onFiltersChange({ category: void 0 })
          }
        ),
        filters.minRating && /* @__PURE__ */ jsxRuntimeExports.jsx(
          FilterTag,
          {
            label: `${filters.minRating}+ stars`,
            onRemove: () => onFiltersChange({ minRating: void 0 })
          }
        ),
        filters.techStack?.map((tech) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          FilterTag,
          {
            label: tech,
            onRemove: () => onFiltersChange({
              techStack: filters.techStack?.filter((t2) => t2 !== tech)
            })
          },
          tech
        ))
      ] })
    ] })
  ] });
}
function FilterSection({ title, isExpanded, onToggle, children }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "border-b border-gray-700 last:border-b-0", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: onToggle,
        className: "w-full flex items-center justify-between p-4 text-sm font-medium hover:bg-gray-800/50 transition-colors",
        children: [
          title,
          isExpanded ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronUp, { className: "w-4 h-4 text-gray-400" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-4 h-4 text-gray-400" })
        ]
      }
    ),
    isExpanded && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "px-4 pb-4", children })
  ] });
}
function FilterTag({ label, onRemove }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "inline-flex items-center gap-1 px-2 py-1 bg-engine-primary/20 text-engine-primary rounded text-xs", children: [
    label,
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      "button",
      {
        onClick: onRemove,
        className: "hover:text-white transition-colors",
        "aria-label": `Remove ${label} filter`,
        children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-3 h-3" })
      }
    )
  ] });
}
function CellCard({
  cell,
  onClick,
  onInstall,
  compact = false,
  className = ""
}) {
  const handleInstallClick = (e) => {
    e.stopPropagation();
    onInstall?.();
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      onClick,
      className: `
        bg-engine-dark
        rounded-lg
        border border-gray-700
        hover:border-gray-600
        transition-all
        ${onClick ? "cursor-pointer hover:shadow-lg" : ""}
        ${compact ? "p-3" : "p-4"}
        ${className}
      `,
      role: onClick ? "button" : void 0,
      tabIndex: onClick ? 0 : void 0,
      onKeyDown: onClick ? (e) => e.key === "Enter" && onClick() : void 0,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start gap-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-shrink-0", children: cell.iconUrl ? /* @__PURE__ */ jsxRuntimeExports.jsx(
            "img",
            {
              src: cell.iconUrl,
              alt: cell.displayName,
              className: `rounded-lg object-cover ${compact ? "w-10 h-10" : "w-12 h-12"}`
            }
          ) : /* @__PURE__ */ jsxRuntimeExports.jsx(
            "div",
            {
              className: `
                rounded-lg
                bg-engine-darker
                flex items-center justify-center
                ${compact ? "w-10 h-10" : "w-12 h-12"}
              `,
              children: /* @__PURE__ */ jsxRuntimeExports.jsx(Box, { className: `text-gray-500 ${compact ? "w-5 h-5" : "w-6 h-6"}` })
            }
          ) }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "h3",
                {
                  className: `
                font-medium text-white truncate
                ${compact ? "text-sm" : "text-base"}
              `,
                  children: cell.displayName
                }
              ),
              cell.author.verified && /* @__PURE__ */ jsxRuntimeExports.jsx(Shield, { className: "w-3.5 h-3.5 text-engine-primary flex-shrink-0" })
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 truncate", children: [
              "by ",
              cell.author.displayName
            ] })
          ] }),
          onInstall && !compact && /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: handleInstallClick,
              className: "\r\n              flex-shrink-0\r\n              px-3 py-1.5\r\n              bg-engine-primary\r\n              hover:bg-blue-600\r\n              rounded\r\n              text-xs\r\n              font-medium\r\n              transition-colors\r\n            ",
              children: "Install"
            }
          )
        ] }),
        !compact && /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "mt-3 text-sm text-gray-400 line-clamp-2", children: cell.description }),
        !compact && cell.tags.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-3 flex flex-wrap gap-1.5", children: [
          cell.tags.slice(0, 3).map((tag) => /* @__PURE__ */ jsxRuntimeExports.jsx(
            "span",
            {
              className: "\r\n                px-2 py-0.5\r\n                bg-engine-darker\r\n                rounded\r\n                text-xs\r\n                text-gray-400\r\n              ",
              children: tag
            },
            tag
          )),
          cell.tags.length > 3 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
            "+",
            cell.tags.length - 3
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `flex items-center gap-4 ${compact ? "mt-2" : "mt-4"}`, children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            RatingDisplay,
            {
              rating: cell.stats.averageRating,
              reviewCount: cell.stats.reviews,
              size: "sm"
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 text-xs text-gray-500", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Download, { className: "w-3 h-3" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: formatNumber(cell.stats.downloads) })
          ] }),
          !compact && /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 text-xs text-gray-500", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Star, { className: "w-3 h-3" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: formatNumber(cell.stats.stars) })
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 text-xs text-gray-500", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(GitFork, { className: "w-3 h-3" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: formatNumber(cell.stats.forks) })
            ] })
          ] })
        ] }),
        !compact && cell.techStack.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mt-3 pt-3 border-t border-gray-700", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-wrap gap-1.5", children: [
          cell.techStack.slice(0, 4).map((tech) => /* @__PURE__ */ jsxRuntimeExports.jsx(
            "span",
            {
              className: "\r\n                  px-2 py-0.5\r\n                  bg-blue-500/10\r\n                  text-blue-400\r\n                  rounded\r\n                  text-xs\r\n                ",
              children: tech
            },
            tech
          )),
          cell.techStack.length > 4 && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs text-gray-500", children: [
            "+",
            cell.techStack.length - 4
          ] })
        ] }) }),
        !compact && cell.repositoryUrl && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mt-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity", children: /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "a",
          {
            href: cell.repositoryUrl,
            target: "_blank",
            rel: "noopener noreferrer",
            onClick: (e) => e.stopPropagation(),
            className: "flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-3 h-3" }),
              "Repository"
            ]
          }
        ) })
      ]
    }
  );
}
function formatNumber(num) {
  if (num >= 1e6) {
    return (num / 1e6).toFixed(1) + "M";
  }
  if (num >= 1e3) {
    return (num / 1e3).toFixed(1) + "K";
  }
  return num.toString();
}
function MarketplaceBrowser({
  onCellClick,
  onCellInstall,
  className = ""
}) {
  const {
    searchQuery,
    searchFilters,
    searchResults,
    totalResults,
    hasMore,
    isSearching,
    searchError,
    trendingCells,
    recentCells,
    topRatedCells,
    featuredLoading,
    categories,
    setSearchQuery,
    setSearchFilters,
    search,
    searchNextPage,
    clearSearch,
    loadFeaturedCells,
    loadCategories
  } = usePortalStore();
  const observerRef = reactExports.useRef(null);
  const loadMoreRef = reactExports.useRef(null);
  reactExports.useEffect(() => {
    loadFeaturedCells();
    loadCategories();
  }, [loadFeaturedCells, loadCategories]);
  reactExports.useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isSearching) {
          searchNextPage();
        }
      },
      { threshold: 0.1 }
    );
    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [hasMore, isSearching, searchNextPage]);
  const handleSearch = reactExports.useCallback(() => {
    search();
  }, [search]);
  const handleQueryChange = reactExports.useCallback(
    (query) => {
      setSearchQuery(query);
      if (query || Object.keys(searchFilters).length > 0) {
        const timer = setTimeout(() => search(), 300);
        return () => clearTimeout(timer);
      }
    },
    [setSearchQuery, search, searchFilters]
  );
  const isSearchMode = searchQuery || Object.keys(searchFilters).length > 0;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `flex gap-6 ${className}`, children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("aside", { className: "w-64 flex-shrink-0", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
      FilterPanel,
      {
        categories,
        filters: searchFilters,
        onFiltersChange: (filters) => {
          setSearchFilters(filters);
          search();
        },
        onClear: clearSearch
      }
    ) }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("main", { className: "flex-1 min-w-0", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mb-6", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
        SearchBar,
        {
          value: searchQuery,
          onChange: handleQueryChange,
          onSearch: handleSearch,
          placeholder: "Search for cells, features, or tech stack...",
          className: "max-w-xl"
        }
      ) }),
      isSearchMode ? (
        // Search Results
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between mb-4", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-medium", children: totalResults > 0 ? `${totalResults.toLocaleString()} results` : "No results found" }),
            isSearching && /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-5 h-5 text-engine-primary animate-spin" })
          ] }),
          searchError && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 mb-4", children: searchError }),
          searchResults.length > 0 ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-4", children: searchResults.map((cell) => /* @__PURE__ */ jsxRuntimeExports.jsx(
            CellCard,
            {
              cell,
              onClick: () => onCellClick?.(cell),
              onInstall: () => onCellInstall?.(cell)
            },
            cell.id
          )) }) : !isSearching && /* @__PURE__ */ jsxRuntimeExports.jsx(
            EmptyState,
            {
              icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Package, { className: "w-12 h-12" }),
              title: "No cells found",
              description: "Try adjusting your search or filters"
            }
          ),
          hasMore && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { ref: loadMoreRef, className: "flex justify-center py-8", children: isSearching && /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-6 h-6 text-engine-primary animate-spin" }) })
        ] })
      ) : (
        // Featured Sections
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-10", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            CellSection,
            {
              icon: /* @__PURE__ */ jsxRuntimeExports.jsx(TrendingUp, { className: "w-5 h-5 text-orange-400" }),
              title: "Trending",
              cells: trendingCells,
              loading: featuredLoading,
              onCellClick,
              onCellInstall
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            CellSection,
            {
              icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Award, { className: "w-5 h-5 text-yellow-400" }),
              title: "Top Rated",
              cells: topRatedCells,
              loading: featuredLoading,
              onCellClick,
              onCellInstall
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            CellSection,
            {
              icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Clock, { className: "w-5 h-5 text-blue-400" }),
              title: "Recently Added",
              cells: recentCells,
              loading: featuredLoading,
              onCellClick,
              onCellInstall
            }
          )
        ] })
      )
    ] })
  ] });
}
function CellSection({
  icon,
  title,
  cells,
  loading,
  onCellClick,
  onCellInstall
}) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("section", { children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 mb-4", children: [
      icon,
      /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-medium", children: title })
    ] }),
    loading ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4", children: Array.from({ length: 4 }).map((_, i) => /* @__PURE__ */ jsxRuntimeExports.jsx(CellCardSkeleton, {}, i)) }) : cells.length > 0 ? /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4", children: cells.map((cell) => /* @__PURE__ */ jsxRuntimeExports.jsx(
      CellCard,
      {
        cell,
        onClick: () => onCellClick?.(cell),
        onInstall: () => onCellInstall?.(cell),
        compact: true
      },
      cell.id
    )) }) : /* @__PURE__ */ jsxRuntimeExports.jsx(
      EmptyState,
      {
        icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Package, { className: "w-8 h-8" }),
        title: "No cells available",
        description: "Check back later for new cells",
        compact: true
      }
    )
  ] });
}
function CellCardSkeleton() {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 p-3 animate-pulse", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start gap-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-10 h-10 bg-gray-700 rounded-lg" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-4 bg-gray-700 rounded w-3/4 mb-2" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-3 bg-gray-700 rounded w-1/2" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-3 flex gap-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-4 bg-gray-700 rounded w-16" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-4 bg-gray-700 rounded w-12" })
    ] })
  ] });
}
function EmptyState({ icon, title, description, compact = false }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: `
        flex flex-col items-center justify-center text-center text-gray-500
        ${compact ? "py-8" : "py-16"}
      `,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mb-3 text-gray-600", children: icon }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: `font-medium ${compact ? "text-sm" : "text-lg"}`, children: title }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: `${compact ? "text-xs" : "text-sm"} mt-1`, children: description })
      ]
    }
  );
}
function ReviewCard({ review, onVote, className = "" }) {
  const [showResponse, setShowResponse] = reactExports.useState(false);
  const [voting, setVoting] = reactExports.useState(false);
  const [localVote, setLocalVote] = reactExports.useState(review.userVote);
  const [helpfulCount, setHelpfulCount] = reactExports.useState(review.helpful);
  const [notHelpfulCount, setNotHelpfulCount] = reactExports.useState(review.notHelpful);
  const handleVote = async (vote) => {
    if (voting || localVote === vote) return;
    setVoting(true);
    try {
      const result = await reviewAPI.vote(review.id, vote);
      setHelpfulCount(result.helpful);
      setNotHelpfulCount(result.notHelpful);
      setLocalVote(vote);
      onVote?.(review.id, vote);
    } catch (error) {
      console.error("Failed to vote:", error);
    } finally {
      setVoting(false);
    }
  };
  const formatDate2 = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric"
    });
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: `bg-engine-dark rounded-lg border border-gray-700 p-4 ${className}`, children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start justify-between mb-3", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
        review.author.avatarUrl ? /* @__PURE__ */ jsxRuntimeExports.jsx(
          "img",
          {
            src: review.author.avatarUrl,
            alt: review.author.displayName,
            className: "w-10 h-10 rounded-full object-cover"
          }
        ) : /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-10 h-10 rounded-full bg-engine-darker flex items-center justify-center text-gray-500 text-sm font-medium", children: review.author.displayName.charAt(0).toUpperCase() }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium text-sm", children: review.author.displayName }),
            review.verified && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-1 text-xs text-green-400", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Shield, { className: "w-3 h-3" }),
              "Verified Install"
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 text-xs text-gray-500", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: formatDate2(review.createdAt) }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
              "v",
              review.cellVersion
            ] })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(StarRating, { rating: review.rating, size: "sm" })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("h4", { className: "font-medium mb-2", children: review.title }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400 whitespace-pre-line", children: review.content }),
    review.authorResponse && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => setShowResponse(!showResponse),
          className: "flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(MessageSquare, { className: "w-3.5 h-3.5" }),
            "Developer Response",
            showResponse ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronUp, { className: "w-3.5 h-3.5" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-3.5 h-3.5" })
          ]
        }
      ),
      showResponse && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-2 pl-4 border-l-2 border-engine-primary", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400", children: review.authorResponse.content }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500 mt-1 block", children: formatDate2(review.authorResponse.respondedAt) })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4 mt-4 pt-3 border-t border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-gray-500", children: "Was this review helpful?" }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => handleVote("helpful"),
          disabled: voting,
          className: `
            flex items-center gap-1 text-xs
            ${localVote === "helpful" ? "text-green-400" : "text-gray-500 hover:text-gray-300"}
            transition-colors disabled:opacity-50
          `,
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(ThumbsUp, { className: "w-3.5 h-3.5" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: helpfulCount })
          ]
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => handleVote("not_helpful"),
          disabled: voting,
          className: `
            flex items-center gap-1 text-xs
            ${localVote === "not_helpful" ? "text-red-400" : "text-gray-500 hover:text-gray-300"}
            transition-colors disabled:opacity-50
          `,
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(ThumbsDown, { className: "w-3.5 h-3.5" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: notHelpfulCount })
          ]
        }
      )
    ] })
  ] });
}
function ReviewList({
  reviews,
  stats,
  loading = false,
  hasMore = false,
  onLoadMore,
  onVote,
  onFilterChange,
  className = ""
}) {
  const [filterRating, setFilterRating] = reactExports.useState();
  const [filterVerified, setFilterVerified] = reactExports.useState(false);
  const handleRatingFilter = (rating) => {
    const newRating = filterRating === rating ? void 0 : rating;
    setFilterRating(newRating);
    onFilterChange?.({ rating: newRating, verified: filterVerified });
  };
  const handleVerifiedFilter = () => {
    const newVerified = !filterVerified;
    setFilterVerified(newVerified);
    onFilterChange?.({ rating: filterRating, verified: newVerified });
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className, children: [
    stats && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "bg-engine-dark rounded-lg border border-gray-700 p-4 mb-6", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start gap-8", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-4xl font-bold text-white", children: stats.averageRating.toFixed(1) }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(StarRating, { rating: stats.averageRating, size: "md", className: "mt-1" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-sm text-gray-500 mt-1", children: [
          stats.totalReviews.toLocaleString(),
          " reviews"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1", children: [5, 4, 3, 2, 1].map((rating) => {
        const count = stats.ratingDistribution[rating];
        const percentage = stats.totalReviews > 0 ? count / stats.totalReviews * 100 : 0;
        return /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => handleRatingFilter(rating),
            className: `
                      flex items-center gap-2 w-full py-1 text-left
                      ${filterRating === rating ? "text-engine-primary" : "text-gray-400 hover:text-white"}
                      transition-colors
                    `,
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-xs w-8", children: [
                rating,
                " star"
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 h-2 bg-gray-700 rounded-full overflow-hidden", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                "div",
                {
                  className: "h-full bg-yellow-400 rounded-full transition-all",
                  style: { width: `${percentage}%` }
                }
              ) }),
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs w-12 text-right", children: count.toLocaleString() })
            ]
          },
          rating
        );
      }) })
    ] }) }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 mb-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Filter, { className: "w-4 h-4 text-gray-500" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-500", children: "Filter:" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          onClick: handleVerifiedFilter,
          className: `
            px-2.5 py-1 rounded text-xs
            ${filterVerified ? "bg-green-500/20 text-green-400" : "bg-engine-dark border border-gray-600 text-gray-400 hover:border-gray-500"}
            transition-colors
          `,
          children: "Verified Only"
        }
      ),
      filterRating && /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => handleRatingFilter(filterRating),
          className: "px-2.5 py-1 bg-engine-primary/20 text-engine-primary rounded text-xs flex items-center gap-1",
          children: [
            filterRating,
            " stars",
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "ml-1", children: "×" })
          ]
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-4", children: reviews.map((review) => /* @__PURE__ */ jsxRuntimeExports.jsx(
      ReviewCard,
      {
        review,
        onVote
      },
      review.id
    )) }),
    !loading && reviews.length === 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center py-12 text-gray-500", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-lg", children: "No reviews yet" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm mt-1", children: "Be the first to review this cell" })
    ] }),
    hasMore && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex justify-center mt-6", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
      "button",
      {
        onClick: onLoadMore,
        disabled: loading,
        className: "\r\n              px-4 py-2\r\n              bg-engine-dark\r\n              border border-gray-600\r\n              rounded-lg\r\n              text-sm\r\n              hover:border-gray-500\r\n              disabled:opacity-50\r\n              transition-colors\r\n            ",
        children: loading ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }) : "Load More Reviews"
      }
    ) })
  ] });
}
function ReviewForm({ cellId, onSubmit, onCancel, className = "" }) {
  const [rating, setRating] = reactExports.useState(0);
  const [title, setTitle] = reactExports.useState("");
  const [content, setContent] = reactExports.useState("");
  const [submitting, setSubmitting] = reactExports.useState(false);
  const [error, setError] = reactExports.useState(null);
  const isValid = rating > 0 && title.trim().length >= 5 && content.trim().length >= 20;
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isValid) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        rating,
        title: title.trim(),
        content: content.trim()
      });
      setRating(0);
      setTitle("");
      setContent("");
    } catch (err) {
      setError(err.message || "Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "form",
    {
      onSubmit: handleSubmit,
      className: `bg-engine-dark rounded-lg border border-gray-700 p-4 ${className}`,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "font-medium mb-4", children: "Write a Review" }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mb-4", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "block text-sm text-gray-400 mb-2", children: [
            "Your Rating ",
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            StarRating,
            {
              rating,
              size: "lg",
              interactive: true,
              onChange: setRating
            }
          ),
          rating === 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-500 mt-1", children: "Click to rate" })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mb-4", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { htmlFor: "review-title", className: "block text-sm text-gray-400 mb-2", children: [
            "Title ",
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "input",
            {
              id: "review-title",
              type: "text",
              value: title,
              onChange: (e) => setTitle(e.target.value),
              placeholder: "Summarize your experience",
              maxLength: 100,
              className: "\r\n            w-full\r\n            px-3 py-2\r\n            bg-engine-darker\r\n            border border-gray-600\r\n            rounded\r\n            text-sm\r\n            placeholder-gray-500\r\n            focus:outline-none\r\n            focus:border-engine-primary\r\n          "
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 mt-1", children: [
            title.length,
            "/100 characters (min 5)"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mb-4", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { htmlFor: "review-content", className: "block text-sm text-gray-400 mb-2", children: [
            "Review ",
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "textarea",
            {
              id: "review-content",
              value: content,
              onChange: (e) => setContent(e.target.value),
              placeholder: "Share your experience with this cell. What worked well? What could be improved?",
              rows: 5,
              maxLength: 2e3,
              className: "\r\n            w-full\r\n            px-3 py-2\r\n            bg-engine-darker\r\n            border border-gray-600\r\n            rounded\r\n            text-sm\r\n            placeholder-gray-500\r\n            resize-none\r\n            focus:outline-none\r\n            focus:border-engine-primary\r\n          "
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-gray-500 mt-1", children: [
            content.length,
            "/2000 characters (min 20)"
          ] })
        ] }),
        error && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400", children: error }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-end gap-3", children: [
          onCancel && /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              type: "button",
              onClick: onCancel,
              disabled: submitting,
              className: "\r\n              px-4 py-2\r\n              text-sm\r\n              text-gray-400\r\n              hover:text-white\r\n              transition-colors\r\n              disabled:opacity-50\r\n            ",
              children: "Cancel"
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              type: "submit",
              disabled: !isValid || submitting,
              className: "\r\n            flex items-center gap-2\r\n            px-4 py-2\r\n            bg-engine-primary\r\n            hover:bg-blue-600\r\n            rounded\r\n            text-sm\r\n            font-medium\r\n            transition-colors\r\n            disabled:opacity-50\r\n            disabled:cursor-not-allowed\r\n          ",
              children: submitting ? /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }),
                "Submitting..."
              ] }) : /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(Send, { className: "w-4 h-4" }),
                "Submit Review"
              ] })
            }
          )
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-4 pt-4 border-t border-gray-700", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("h4", { className: "text-xs text-gray-500 mb-2", children: "Review Guidelines" }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("ul", { className: "text-xs text-gray-600 space-y-1", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("li", { children: "Be specific about what you liked or disliked" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("li", { children: "Mention the version you used" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("li", { children: "Keep it constructive and helpful for others" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("li", { children: "Avoid personal attacks or inappropriate content" })
          ] })
        ] })
      ]
    }
  );
}
function CellDetailModal({ cell, onClose, onInstall }) {
  const [activeTab, setActiveTab] = reactExports.useState("overview");
  const [selectedVersion, setSelectedVersion] = reactExports.useState(cell.currentVersion);
  const [installing, setInstalling] = reactExports.useState(false);
  const [installResult, setInstallResult] = reactExports.useState(null);
  const {
    selectedCellReviews,
    selectedCellReviewStats,
    loadCellReviews,
    installCell
  } = usePortalStore();
  reactExports.useEffect(() => {
    if (activeTab === "reviews") {
      loadCellReviews(cell.id);
    }
  }, [activeTab, cell.id, loadCellReviews]);
  reactExports.useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);
  const handleInstall = async () => {
    setInstalling(true);
    setInstallResult(null);
    try {
      const result = await installCell(cell.id, selectedVersion);
      setInstallResult(result);
      onInstall?.(cell, selectedVersion);
    } catch (error) {
      setInstallResult({ success: false, message: error.message });
    } finally {
      setInstalling(false);
    }
  };
  const handleReviewSubmit = async (data) => {
    await reviewAPI.submit(cell.id, data);
    loadCellReviews(cell.id);
  };
  const selectedVersionData = cell.versions.find((v2) => v2.version === selectedVersion);
  return /* @__PURE__ */ jsxRuntimeExports.jsx(
    "div",
    {
      className: "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60",
      onClick: onClose,
      children: /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "div",
        {
          className: "bg-engine-darker rounded-xl border border-gray-700 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col",
          onClick: (e) => e.stopPropagation(),
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-start gap-4 p-6 border-b border-gray-700", children: [
              cell.iconUrl ? /* @__PURE__ */ jsxRuntimeExports.jsx(
                "img",
                {
                  src: cell.iconUrl,
                  alt: cell.displayName,
                  className: "w-16 h-16 rounded-xl object-cover"
                }
              ) : /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-16 h-16 rounded-xl bg-engine-dark flex items-center justify-center", children: /* @__PURE__ */ jsxRuntimeExports.jsx(Box, { className: "w-8 h-8 text-gray-500" }) }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-xl font-semibold", children: cell.displayName }),
                  cell.author.verified && /* @__PURE__ */ jsxRuntimeExports.jsx(Shield, { className: "w-5 h-5 text-engine-primary" })
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-sm text-gray-400 mt-1", children: [
                  "by ",
                  cell.author.displayName,
                  " · ",
                  cell.namespace
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4 mt-2", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    RatingDisplay,
                    {
                      rating: cell.stats.averageRating,
                      reviewCount: cell.stats.reviews
                    }
                  ),
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1 text-sm text-gray-500", children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx(Download, { className: "w-4 h-4" }),
                    cell.stats.downloads.toLocaleString(),
                    " downloads"
                  ] })
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex flex-col items-end gap-2", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative", children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "select",
                      {
                        value: selectedVersion,
                        onChange: (e) => setSelectedVersion(e.target.value),
                        className: "\r\n                    appearance-none\r\n                    pl-3 pr-8 py-2\r\n                    bg-engine-dark\r\n                    border border-gray-600\r\n                    rounded\r\n                    text-sm\r\n                    focus:outline-none\r\n                    focus:border-engine-primary\r\n                  ",
                        children: cell.versions.map((v2) => /* @__PURE__ */ jsxRuntimeExports.jsxs("option", { value: v2.version, children: [
                          "v",
                          v2.version
                        ] }, v2.version))
                      }
                    ),
                    /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" })
                  ] }),
                  /* @__PURE__ */ jsxRuntimeExports.jsxs(
                    "button",
                    {
                      onClick: handleInstall,
                      disabled: installing,
                      className: "\r\n                  flex items-center gap-2\r\n                  px-4 py-2\r\n                  bg-engine-primary\r\n                  hover:bg-blue-600\r\n                  rounded\r\n                  font-medium\r\n                  transition-colors\r\n                  disabled:opacity-50\r\n                ",
                      children: [
                        installing ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Download, { className: "w-4 h-4" }),
                        "Install"
                      ]
                    }
                  )
                ] }),
                installResult && /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "div",
                  {
                    className: `text-xs flex items-center gap-1 ${installResult.success ? "text-green-400" : "text-red-400"}`,
                    children: installResult.success ? /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
                      /* @__PURE__ */ jsxRuntimeExports.jsx(Check, { className: "w-3 h-3" }),
                      "Installed successfully"
                    ] }) : /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
                      /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: "w-3 h-3" }),
                      installResult.message || "Install failed"
                    ] })
                  }
                )
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: onClose,
                  className: "p-1 text-gray-400 hover:text-white transition-colors",
                  children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-5 h-5" })
                }
              )
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex border-b border-gray-700", children: ["overview", "versions", "reviews", "dependencies"].map(
              (tab) => /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: () => setActiveTab(tab),
                  className: `
                  px-4 py-3 text-sm font-medium capitalize
                  ${activeTab === tab ? "text-engine-primary border-b-2 border-engine-primary" : "text-gray-400 hover:text-white"}
                  transition-colors
                `,
                  children: tab
                },
                tab
              )
            ) }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-auto p-6", children: [
              activeTab === "overview" && /* @__PURE__ */ jsxRuntimeExports.jsx(OverviewTab, { cell, selectedVersion: selectedVersionData }),
              activeTab === "versions" && /* @__PURE__ */ jsxRuntimeExports.jsx(VersionsTab, { cell }),
              activeTab === "reviews" && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-6", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(ReviewForm, { cellId: cell.id, onSubmit: handleReviewSubmit }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(
                  ReviewList,
                  {
                    reviews: selectedCellReviews,
                    stats: selectedCellReviewStats,
                    onLoadMore: () => loadCellReviews(cell.id, 2)
                  }
                )
              ] }),
              activeTab === "dependencies" && /* @__PURE__ */ jsxRuntimeExports.jsx(DependenciesTab, { cell })
            ] })
          ]
        }
      )
    }
  );
}
function OverviewTab({
  cell,
  selectedVersion
}) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-3 gap-6", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "col-span-2 space-y-6", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "font-medium mb-2", children: "Description" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400 whitespace-pre-line", children: cell.longDescription || cell.description })
      ] }),
      cell.screenshotUrls.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "font-medium mb-2", children: "Screenshots" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex gap-2 overflow-x-auto pb-2", children: cell.screenshotUrls.map((url, i) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          "img",
          {
            src: url,
            alt: `Screenshot ${i + 1}`,
            className: "h-40 rounded-lg object-cover"
          },
          i
        )) })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "space-y-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 p-4 space-y-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(InfoRow, { label: "Category", value: cell.category }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(InfoRow, { label: "License", value: cell.license }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(InfoRow, { label: "Version", value: `v${cell.currentVersion}` }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          InfoRow,
          {
            label: "Published",
            value: cell.publishedAt ? formatDate(cell.publishedAt) : "N/A"
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx(InfoRow, { label: "Updated", value: formatDate(cell.updatedAt) }),
        selectedVersion && /* @__PURE__ */ jsxRuntimeExports.jsx(
          InfoRow,
          {
            label: "Security Score",
            value: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                Shield,
                {
                  className: `w-4 h-4 ${selectedVersion.securityScore >= 80 ? "text-green-400" : selectedVersion.securityScore >= 60 ? "text-yellow-400" : "text-red-400"}`
                }
              ),
              selectedVersion.securityScore,
              "/100"
            ] })
          }
        )
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 p-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h4", { className: "text-sm font-medium mb-2", children: "Tags" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5", children: cell.tags.map((tag) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          "span",
          {
            className: "px-2 py-0.5 bg-engine-darker rounded text-xs text-gray-400",
            children: tag
          },
          tag
        )) })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 p-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h4", { className: "text-sm font-medium mb-2", children: "Tech Stack" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5", children: cell.techStack.map((tech) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          "span",
          {
            className: "px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded text-xs",
            children: tech
          },
          tech
        )) })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-dark rounded-lg border border-gray-700 p-4 space-y-2", children: [
        cell.repositoryUrl && /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "a",
          {
            href: cell.repositoryUrl,
            target: "_blank",
            rel: "noopener noreferrer",
            className: "flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(GitBranch, { className: "w-4 h-4" }),
              "Repository",
              /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-3 h-3 ml-auto" })
            ]
          }
        ),
        cell.documentationUrl && /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "a",
          {
            href: cell.documentationUrl,
            target: "_blank",
            rel: "noopener noreferrer",
            className: "flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(FileText, { className: "w-4 h-4" }),
              "Documentation",
              /* @__PURE__ */ jsxRuntimeExports.jsx(ExternalLink, { className: "w-3 h-3 ml-auto" })
            ]
          }
        )
      ] })
    ] })
  ] });
}
function VersionsTab({ cell }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-4", children: cell.versions.map((version) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: "bg-engine-dark rounded-lg border border-gray-700 p-4",
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between mb-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "font-medium", children: [
              "v",
              version.version
            ] }),
            version.version === cell.currentVersion && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs", children: "Latest" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx(
              "span",
              {
                className: `px-2 py-0.5 rounded text-xs ${version.validationStatus === "passed" ? "bg-green-500/20 text-green-400" : version.validationStatus === "failed" ? "bg-red-500/20 text-red-400" : "bg-gray-500/20 text-gray-400"}`,
                children: version.validationStatus
              }
            )
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-500", children: formatDate(version.releaseDate) })
        ] }),
        version.changelog && /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-gray-400 whitespace-pre-line", children: version.changelog }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4 mt-3 text-xs text-gray-500", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            version.downloadCount.toLocaleString(),
            " downloads"
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
            "Security: ",
            version.securityScore,
            "/100"
          ] })
        ] })
      ]
    },
    version.version
  )) });
}
function DependenciesTab({ cell }) {
  if (cell.dependencies.length === 0) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center py-12 text-gray-500", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Box, { className: "w-12 h-12 mx-auto mb-3 opacity-50" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "No dependencies" })
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-3", children: cell.dependencies.map((dep) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: "bg-engine-dark rounded-lg border border-gray-700 p-4 flex items-center justify-between",
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium", children: dep.cellName }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm text-gray-500 ml-2", children: dep.versionConstraint })
        ] }),
        dep.optional && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "px-2 py-0.5 bg-gray-500/20 text-gray-400 rounded text-xs", children: "optional" })
      ]
    },
    dep.cellId
  )) });
}
function InfoRow({ label, value }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between text-sm", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: label }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-300", children: value })
  ] });
}
function formatDate(dateString) {
  return new Date(dateString).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric"
  });
}
function TenantSwitcher({ className = "" }) {
  const [isOpen, setIsOpen] = reactExports.useState(false);
  const [showCreateForm, setShowCreateForm] = reactExports.useState(false);
  const dropdownRef = reactExports.useRef(null);
  const {
    tenants,
    activeTenantId,
    isLoading,
    switchTenant,
    createTenant,
    getActiveTenant
  } = useTenantStore();
  const activeTenant = getActiveTenant();
  reactExports.useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
        setShowCreateForm(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  const handleTenantSelect = (tenantId) => {
    switchTenant(tenantId);
    setIsOpen(false);
  };
  const handleCreateTenant = async (name, displayName) => {
    const tenant = await createTenant({ name, displayName });
    if (tenant) {
      setShowCreateForm(false);
    }
  };
  if (tenants.length === 0 && !isLoading) {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: () => setIsOpen(true),
        className: `
          flex items-center gap-2 px-3 py-2
          bg-engine-dark border border-gray-600
          rounded-lg text-sm
          hover:border-gray-500
          transition-colors
          ${className}
        `,
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-4 h-4" }),
          "Create Organization"
        ]
      }
    );
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { ref: dropdownRef, className: `relative ${className}`, children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: () => setIsOpen(!isOpen),
        disabled: isLoading,
        className: "\r\n          flex items-center gap-2 px-3 py-2\r\n          bg-engine-dark border border-gray-600\r\n          rounded-lg text-sm\r\n          hover:border-gray-500\r\n          transition-colors\r\n          min-w-[180px]\r\n        ",
        children: [
          activeTenant?.logoUrl ? /* @__PURE__ */ jsxRuntimeExports.jsx(
            "img",
            {
              src: activeTenant.logoUrl,
              alt: activeTenant.displayName,
              className: "w-5 h-5 rounded"
            }
          ) : /* @__PURE__ */ jsxRuntimeExports.jsx(Building2, { className: "w-4 h-4 text-gray-400" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "flex-1 text-left truncate", children: activeTenant?.displayName || "Select Organization" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            ChevronDown,
            {
              className: `w-4 h-4 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`
            }
          )
        ]
      }
    ),
    isOpen && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "absolute top-full left-0 mt-1 w-64 bg-engine-dark border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "max-h-60 overflow-y-auto", children: tenants.map((tenant) => /* @__PURE__ */ jsxRuntimeExports.jsx(
        TenantItem,
        {
          tenant,
          isActive: tenant.id === activeTenantId,
          onClick: () => handleTenantSelect(tenant.id)
        },
        tenant.id
      )) }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "border-t border-gray-700" }),
      showCreateForm ? /* @__PURE__ */ jsxRuntimeExports.jsx(
        CreateTenantForm,
        {
          onSubmit: handleCreateTenant,
          onCancel: () => setShowCreateForm(false)
        }
      ) : /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: () => setShowCreateForm(true),
          className: "\r\n                w-full flex items-center gap-2 px-4 py-3\r\n                text-sm text-gray-400\r\n                hover:bg-gray-800 hover:text-white\r\n                transition-colors\r\n              ",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-4 h-4" }),
            "Create Organization"
          ]
        }
      )
    ] })
  ] });
}
function TenantItem({ tenant, isActive, onClick }) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "button",
    {
      onClick,
      className: `
        w-full flex items-center gap-3 px-4 py-3
        text-left
        ${isActive ? "bg-engine-primary/10" : "hover:bg-gray-800"}
        transition-colors
      `,
      children: [
        tenant.logoUrl ? /* @__PURE__ */ jsxRuntimeExports.jsx(
          "img",
          {
            src: tenant.logoUrl,
            alt: tenant.displayName,
            className: "w-8 h-8 rounded"
          }
        ) : /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "w-8 h-8 rounded bg-engine-darker flex items-center justify-center", children: /* @__PURE__ */ jsxRuntimeExports.jsx(Building2, { className: "w-4 h-4 text-gray-500" }) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-sm font-medium truncate", children: tenant.displayName }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-xs text-gray-500 truncate", children: tenant.name })
        ] }),
        isActive && /* @__PURE__ */ jsxRuntimeExports.jsx(Check, { className: "w-4 h-4 text-engine-primary flex-shrink-0" })
      ]
    }
  );
}
function CreateTenantForm({ onSubmit, onCancel }) {
  const [name, setName] = reactExports.useState("");
  const [displayName, setDisplayName] = reactExports.useState("");
  const [submitting, setSubmitting] = reactExports.useState(false);
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !displayName.trim()) return;
    setSubmitting(true);
    await onSubmit(name.trim(), displayName.trim());
    setSubmitting(false);
  };
  const handleDisplayNameChange = (value) => {
    setDisplayName(value);
    if (!name || name === toSlug$1(displayName)) {
      setName(toSlug$1(value));
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("form", { onSubmit: handleSubmit, className: "p-4 space-y-3", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-xs text-gray-500 mb-1", children: "Display Name" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "input",
        {
          type: "text",
          value: displayName,
          onChange: (e) => handleDisplayNameChange(e.target.value),
          placeholder: "My Organization",
          className: "\r\n            w-full px-3 py-2\r\n            bg-engine-darker border border-gray-600\r\n            rounded text-sm\r\n            focus:outline-none focus:border-engine-primary\r\n          "
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-xs text-gray-500 mb-1", children: "URL Name" }),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "input",
        {
          type: "text",
          value: name,
          onChange: (e) => setName(toSlug$1(e.target.value)),
          placeholder: "my-organization",
          className: "\r\n            w-full px-3 py-2\r\n            bg-engine-darker border border-gray-600\r\n            rounded text-sm\r\n            focus:outline-none focus:border-engine-primary\r\n          "
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-end gap-2 pt-2", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          type: "button",
          onClick: onCancel,
          className: "px-3 py-1.5 text-sm text-gray-400 hover:text-white",
          children: "Cancel"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        "button",
        {
          type: "submit",
          disabled: !name.trim() || !displayName.trim() || submitting,
          className: "\r\n            px-3 py-1.5\r\n            bg-engine-primary hover:bg-blue-600\r\n            rounded text-sm font-medium\r\n            disabled:opacity-50\r\n            transition-colors\r\n          ",
          children: "Create"
        }
      )
    ] })
  ] });
}
function toSlug$1(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
const CATEGORIES = [
  "API",
  "Authentication",
  "Database",
  "DevOps",
  "Frontend",
  "Backend",
  "Analytics",
  "AI/ML",
  "Communication",
  "Storage",
  "Security",
  "Utility"
];
const LICENSES = [
  "MIT",
  "Apache-2.0",
  "GPL-3.0",
  "BSD-3-Clause",
  "ISC",
  "Proprietary"
];
function PublishCellModal({ onClose, onSuccess }) {
  const { activeTenantId } = useTenantStore();
  const [formData, setFormData] = reactExports.useState({
    visibility: "public",
    tags: [],
    techStack: [],
    license: "MIT"
  });
  const [iconPreview, setIconPreview] = reactExports.useState(null);
  const [screenshotPreviews, setScreenshotPreviews] = reactExports.useState([]);
  const [tagInput, setTagInput] = reactExports.useState("");
  const [techInput, setTechInput] = reactExports.useState("");
  const [submitting, setSubmitting] = reactExports.useState(false);
  const [error, setError] = reactExports.useState(null);
  const iconInputRef = reactExports.useRef(null);
  const screenshotInputRef = reactExports.useRef(null);
  const updateField = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };
  const handleIconChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      updateField("iconFile", file);
      setIconPreview(URL.createObjectURL(file));
    }
  };
  const handleScreenshotsChange = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length) {
      const current = formData.screenshotFiles || [];
      const newFiles = [...current, ...files].slice(0, 5);
      updateField("screenshotFiles", newFiles);
      setScreenshotPreviews(newFiles.map((f2) => URL.createObjectURL(f2)));
    }
  };
  const removeScreenshot = (index) => {
    const newFiles = [...formData.screenshotFiles || []];
    newFiles.splice(index, 1);
    updateField("screenshotFiles", newFiles);
    const newPreviews = [...screenshotPreviews];
    URL.revokeObjectURL(newPreviews[index]);
    newPreviews.splice(index, 1);
    setScreenshotPreviews(newPreviews);
  };
  const addTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !formData.tags?.includes(tag)) {
      updateField("tags", [...formData.tags || [], tag]);
    }
    setTagInput("");
  };
  const removeTag = (tag) => {
    updateField("tags", formData.tags?.filter((t2) => t2 !== tag) || []);
  };
  const addTech = () => {
    const tech = techInput.trim();
    if (tech && !formData.techStack?.includes(tech)) {
      updateField("techStack", [...formData.techStack || [], tech]);
    }
    setTechInput("");
  };
  const removeTech = (tech) => {
    updateField("techStack", formData.techStack?.filter((t2) => t2 !== tech) || []);
  };
  const isValid = formData.name && formData.displayName && formData.description && formData.category && formData.license;
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isValid || !activeTenantId) return;
    setSubmitting(true);
    setError(null);
    try {
      await publicationAPI.publishCell(formData, activeTenantId);
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err.message || "Failed to publish cell");
    } finally {
      setSubmitting(false);
    }
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsx(
    "div",
    {
      className: "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60",
      onClick: onClose,
      children: /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "div",
        {
          className: "bg-engine-darker rounded-xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col",
          onClick: (e) => e.stopPropagation(),
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-between px-6 py-4 border-b border-gray-700", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-semibold", children: "Publish New Cell" }),
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: onClose,
                  className: "p-1 text-gray-400 hover:text-white transition-colors",
                  children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-5 h-5" })
                }
              )
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("form", { onSubmit: handleSubmit, className: "flex-1 overflow-auto p-6 space-y-5", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-4", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-shrink-0", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "input",
                    {
                      ref: iconInputRef,
                      type: "file",
                      accept: "image/*",
                      onChange: handleIconChange,
                      className: "hidden"
                    }
                  ),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "button",
                    {
                      type: "button",
                      onClick: () => iconInputRef.current?.click(),
                      className: "\r\n                  w-20 h-20 rounded-xl\r\n                  bg-engine-dark border border-gray-600 border-dashed\r\n                  flex items-center justify-center\r\n                  hover:border-gray-500\r\n                  transition-colors overflow-hidden\r\n                ",
                      children: iconPreview ? /* @__PURE__ */ jsxRuntimeExports.jsx(
                        "img",
                        {
                          src: iconPreview,
                          alt: "Icon preview",
                          className: "w-full h-full object-cover"
                        }
                      ) : /* @__PURE__ */ jsxRuntimeExports.jsx(Image$1, { className: "w-8 h-8 text-gray-500" })
                    }
                  ),
                  /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-gray-500 mt-1 text-center", children: "Icon" })
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 space-y-3", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "block text-sm text-gray-400 mb-1", children: [
                      "Display Name ",
                      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
                    ] }),
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "input",
                      {
                        type: "text",
                        value: formData.displayName || "",
                        onChange: (e) => {
                          updateField("displayName", e.target.value);
                          if (!formData.name) {
                            updateField("name", toSlug(e.target.value));
                          }
                        },
                        placeholder: "My Awesome Cell",
                        className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                      }
                    )
                  ] }),
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "block text-sm text-gray-400 mb-1", children: [
                      "URL Name ",
                      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
                    ] }),
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "input",
                      {
                        type: "text",
                        value: formData.name || "",
                        onChange: (e) => updateField("name", toSlug(e.target.value)),
                        placeholder: "my-awesome-cell",
                        className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                      }
                    )
                  ] })
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "block text-sm text-gray-400 mb-1", children: [
                  "Short Description ",
                  /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "input",
                  {
                    type: "text",
                    value: formData.description || "",
                    onChange: (e) => updateField("description", e.target.value),
                    placeholder: "A brief description of your cell",
                    maxLength: 200,
                    className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                  }
                )
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-1", children: "Long Description" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "textarea",
                  {
                    value: formData.longDescription || "",
                    onChange: (e) => updateField("longDescription", e.target.value),
                    placeholder: "Detailed description with features, use cases, etc.",
                    rows: 4,
                    className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary resize-none"
                  }
                )
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-4", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "block text-sm text-gray-400 mb-1", children: [
                    "Category ",
                    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
                  ] }),
                  /* @__PURE__ */ jsxRuntimeExports.jsxs(
                    "select",
                    {
                      value: formData.category || "",
                      onChange: (e) => updateField("category", e.target.value),
                      className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary",
                      children: [
                        /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: "", children: "Select category" }),
                        CATEGORIES.map((cat) => /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: cat, children: cat }, cat))
                      ]
                    }
                  )
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("label", { className: "block text-sm text-gray-400 mb-1", children: [
                    "License ",
                    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400", children: "*" })
                  ] }),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "select",
                    {
                      value: formData.license || "",
                      onChange: (e) => updateField("license", e.target.value),
                      className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary",
                      children: LICENSES.map((lic) => /* @__PURE__ */ jsxRuntimeExports.jsx("option", { value: lic, children: lic }, lic))
                    }
                  )
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-2", children: "Visibility" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex gap-3", children: ["public", "unlisted", "private"].map((vis) => /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "button",
                  {
                    type: "button",
                    onClick: () => updateField("visibility", vis),
                    className: `
                    px-4 py-2 rounded text-sm capitalize
                    ${formData.visibility === vis ? "bg-engine-primary text-white" : "bg-engine-dark border border-gray-600 text-gray-400 hover:border-gray-500"}
                    transition-colors
                  `,
                    children: vis
                  },
                  vis
                )) })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-1", children: "Tags" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-2 mb-2", children: formData.tags?.map((tag) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
                  "span",
                  {
                    className: "inline-flex items-center gap-1 px-2 py-1 bg-engine-dark border border-gray-600 rounded text-xs",
                    children: [
                      tag,
                      /* @__PURE__ */ jsxRuntimeExports.jsx("button", { type: "button", onClick: () => removeTag(tag), children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-3 h-3" }) })
                    ]
                  },
                  tag
                )) }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "input",
                    {
                      type: "text",
                      value: tagInput,
                      onChange: (e) => setTagInput(e.target.value),
                      onKeyDown: (e) => e.key === "Enter" && (e.preventDefault(), addTag()),
                      placeholder: "Add tag",
                      className: "flex-1 px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                    }
                  ),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "button",
                    {
                      type: "button",
                      onClick: addTag,
                      className: "px-3 py-2 bg-engine-dark border border-gray-600 rounded hover:border-gray-500",
                      children: /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-4 h-4" })
                    }
                  )
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-1", children: "Tech Stack" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-2 mb-2", children: formData.techStack?.map((tech) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
                  "span",
                  {
                    className: "inline-flex items-center gap-1 px-2 py-1 bg-blue-500/10 text-blue-400 rounded text-xs",
                    children: [
                      tech,
                      /* @__PURE__ */ jsxRuntimeExports.jsx("button", { type: "button", onClick: () => removeTech(tech), children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-3 h-3" }) })
                    ]
                  },
                  tech
                )) }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "input",
                    {
                      type: "text",
                      value: techInput,
                      onChange: (e) => setTechInput(e.target.value),
                      onKeyDown: (e) => e.key === "Enter" && (e.preventDefault(), addTech()),
                      placeholder: "Add technology",
                      className: "flex-1 px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                    }
                  ),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "button",
                    {
                      type: "button",
                      onClick: addTech,
                      className: "px-3 py-2 bg-engine-dark border border-gray-600 rounded hover:border-gray-500",
                      children: /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-4 h-4" })
                    }
                  )
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "grid grid-cols-2 gap-4", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-1", children: "Repository URL" }),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "input",
                    {
                      type: "url",
                      value: formData.repositoryUrl || "",
                      onChange: (e) => updateField("repositoryUrl", e.target.value),
                      placeholder: "https://github.com/...",
                      className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                    }
                  )
                ] }),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-1", children: "Documentation URL" }),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "input",
                    {
                      type: "url",
                      value: formData.documentationUrl || "",
                      onChange: (e) => updateField("documentationUrl", e.target.value),
                      placeholder: "https://docs.example.com",
                      className: "w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                    }
                  )
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx("label", { className: "block text-sm text-gray-400 mb-2", children: "Screenshots (max 5)" }),
                /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "input",
                  {
                    ref: screenshotInputRef,
                    type: "file",
                    accept: "image/*",
                    multiple: true,
                    onChange: handleScreenshotsChange,
                    className: "hidden"
                  }
                ),
                /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-2 overflow-x-auto pb-2", children: [
                  screenshotPreviews.map((url, i) => /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative flex-shrink-0", children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "img",
                      {
                        src: url,
                        alt: `Screenshot ${i + 1}`,
                        className: "h-24 rounded-lg object-cover"
                      }
                    ),
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "button",
                      {
                        type: "button",
                        onClick: () => removeScreenshot(i),
                        className: "absolute -top-2 -right-2 p-1 bg-red-500 rounded-full",
                        children: /* @__PURE__ */ jsxRuntimeExports.jsx(Trash2, { className: "w-3 h-3" })
                      }
                    )
                  ] }, i)),
                  screenshotPreviews.length < 5 && /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "button",
                    {
                      type: "button",
                      onClick: () => screenshotInputRef.current?.click(),
                      className: "\r\n                    h-24 w-24 flex-shrink-0\r\n                    bg-engine-dark border border-gray-600 border-dashed\r\n                    rounded-lg flex items-center justify-center\r\n                    hover:border-gray-500 transition-colors\r\n                  ",
                      children: /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-6 h-6 text-gray-500" })
                    }
                  )
                ] })
              ] }),
              error && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400", children: error })
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-700", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  type: "button",
                  onClick: onClose,
                  className: "px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors",
                  children: "Cancel"
                }
              ),
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: handleSubmit,
                  disabled: !isValid || submitting,
                  className: "\r\n              flex items-center gap-2\r\n              px-4 py-2\r\n              bg-engine-primary hover:bg-blue-600\r\n              rounded font-medium text-sm\r\n              disabled:opacity-50\r\n              transition-colors\r\n            ",
                  children: submitting ? /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-4 h-4 animate-spin" }),
                    "Publishing..."
                  ] }) : /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx(Upload, { className: "w-4 h-4" }),
                    "Publish Cell"
                  ] })
                }
              )
            ] })
          ]
        }
      )
    }
  );
}
function toSlug(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
function PortalPage() {
  const [selectedCell, setSelectedCell] = reactExports.useState(null);
  const [showPublishModal, setShowPublishModal] = reactExports.useState(false);
  const { selectCell, loadCellDetail } = usePortalStore();
  const { loadTenants, activeTenantId } = useTenantStore();
  reactExports.useEffect(() => {
    loadTenants();
  }, [loadTenants]);
  const handleCellClick = (cell) => {
    setSelectedCell(cell);
    selectCell(cell);
    loadCellDetail(cell.id);
  };
  const handleCellInstall = (cell) => {
    handleCellClick(cell);
  };
  const handleCloseDetail = () => {
    setSelectedCell(null);
    selectCell(null);
  };
  const handlePublishSuccess = () => {
    setShowPublishModal(false);
    usePortalStore.getState().loadFeaturedCells();
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-full flex flex-col bg-engine-darker", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("header", { className: "flex items-center justify-between px-6 py-4 border-b border-gray-700", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(Store, { className: "w-6 h-6 text-engine-primary" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("h1", { className: "text-xl font-semibold", children: "Cell Marketplace" })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(TenantSwitcher, {}),
        activeTenantId && /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: () => setShowPublishModal(true),
            className: "\r\n                flex items-center gap-2\r\n                px-4 py-2\r\n                bg-engine-primary\r\n                hover:bg-blue-600\r\n                rounded-lg\r\n                font-medium\r\n                transition-colors\r\n              ",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Plus, { className: "w-4 h-4" }),
              "Publish Cell"
            ]
          }
        )
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntimeExports.jsx("main", { className: "flex-1 overflow-auto p-6", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
      MarketplaceBrowser,
      {
        onCellClick: handleCellClick,
        onCellInstall: handleCellInstall
      }
    ) }),
    selectedCell && /* @__PURE__ */ jsxRuntimeExports.jsx(
      CellDetailModal,
      {
        cell: selectedCell,
        onClose: handleCloseDetail,
        onInstall: (cell, version) => {
          console.log("Installing:", cell.name, version);
        }
      }
    ),
    showPublishModal && /* @__PURE__ */ jsxRuntimeExports.jsx(
      PublishCellModal,
      {
        onClose: () => setShowPublishModal(false),
        onSuccess: handlePublishSuccess
      }
    )
  ] });
}
const defaultStatus = {
  fastapi: { name: "FastAPI", status: "stopped" },
  docker: { name: "Docker", status: "stopped" },
  python: { name: "Python", status: "stopped" }
};
function ServiceStatusBar() {
  const [services, setServices] = reactExports.useState(defaultStatus);
  const [expanded, setExpanded] = reactExports.useState(false);
  const [restarting, setRestarting] = reactExports.useState(false);
  reactExports.useEffect(() => {
    window.electronAPI?.services?.getStatus?.().then((status) => {
      if (status) setServices(status);
    }).catch(() => {
    });
    const cleanup = window.electronAPI?.services?.onStatusUpdate?.((status) => {
      if (status) setServices(status);
    });
    return () => {
      cleanup?.();
    };
  }, []);
  const handleRestart = async () => {
    setRestarting(true);
    try {
      const status = await window.electronAPI?.services?.restartFastAPI?.();
      if (status) setServices(status);
    } catch (err) {
      console.error("Failed to restart services:", err);
    } finally {
      setRestarting(false);
    }
  };
  const allRunning = services.fastapi.status === "running" && services.python.status === "running";
  const hasErrors = services.fastapi.status === "error" || services.python.status === "error";
  const isStarting = services.fastapi.status === "starting";
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "bg-engine-darker border-t border-gray-700", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "button",
      {
        onClick: () => setExpanded(!expanded),
        className: "w-full flex items-center justify-between px-4 py-1.5 text-xs hover:bg-gray-800/50 transition",
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
            isStarting ? /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 text-yellow-500 animate-spin" }) : allRunning ? /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle, { className: "w-3.5 h-3.5 text-green-500" }) : hasErrors ? /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-3.5 h-3.5 text-red-500" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3.5 h-3.5 text-gray-500 animate-spin" }),
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-400", children: isStarting ? "Starting services..." : allRunning ? "All services running" : hasErrors ? "Service issues detected" : "Checking services..." }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 ml-2", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(StatusPill, { name: "API", status: services.fastapi.status }),
              /* @__PURE__ */ jsxRuntimeExports.jsx(StatusPill, { name: "Docker", status: services.docker.status }),
              /* @__PURE__ */ jsxRuntimeExports.jsx(StatusPill, { name: "Python", status: services.python.status })
            ] })
          ] }),
          expanded ? /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronDown, { className: "w-3.5 h-3.5 text-gray-500" }) : /* @__PURE__ */ jsxRuntimeExports.jsx(ChevronUp, { className: "w-3.5 h-3.5 text-gray-500" })
        ]
      }
    ),
    expanded && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 pb-3 pt-1 space-y-2 border-t border-gray-700/50", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        ServiceRow,
        {
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Server, { className: "w-4 h-4" }),
          service: services.fastapi,
          detail: services.fastapi.url || `Port 8000`
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        ServiceRow,
        {
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Container, { className: "w-4 h-4" }),
          service: services.docker,
          detail: "VNC sandbox & preview"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx(
        ServiceRow,
        {
          icon: /* @__PURE__ */ jsxRuntimeExports.jsx(Code2, { className: "w-4 h-4" }),
          service: services.python,
          detail: "Python runtime"
        }
      ),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex justify-end pt-1", children: /* @__PURE__ */ jsxRuntimeExports.jsxs(
        "button",
        {
          onClick: handleRestart,
          disabled: restarting,
          className: "flex items-center gap-1.5 px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded transition disabled:opacity-50",
          children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(RefreshCw, { className: `w-3 h-3 ${restarting ? "animate-spin" : ""}` }),
            restarting ? "Restarting..." : "Restart Services"
          ]
        }
      ) })
    ] })
  ] });
}
function StatusPill({ name, status }) {
  const colorClass = status === "running" ? "bg-green-500/20 text-green-400" : status === "starting" ? "bg-yellow-500/20 text-yellow-400" : status === "error" ? "bg-red-500/20 text-red-400" : "bg-gray-500/20 text-gray-500";
  return /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: `px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClass}`, children: name });
}
function ServiceRow({
  icon,
  service,
  detail
}) {
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 text-xs", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-gray-400", children: icon }),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium text-gray-200", children: service.name }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(StatusBadge, { status: service.status })
      ] }),
      service.error ? /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-red-400 mt-0.5 text-[11px]", children: service.error }) : /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-gray-500 mt-0.5", children: detail })
    ] })
  ] });
}
function StatusBadge({ status }) {
  if (status === "running") {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-1 text-green-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" }),
      "Running"
    ] });
  }
  if (status === "starting") {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-1 text-yellow-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(Loader2, { className: "w-3 h-3 animate-spin" }),
      "Starting"
    ] });
  }
  if (status === "error") {
    return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-1 text-red-400", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx(XCircle, { className: "w-3 h-3" }),
      "Error"
    ] });
  }
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-1 text-gray-500", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "w-1.5 h-1.5 bg-gray-500 rounded-full" }),
    "Stopped"
  ] });
}
const ClarificationBadge = ({
  count,
  highPriorityCount = 0,
  onClick
}) => {
  if (count === 0) return null;
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "button",
    {
      onClick,
      className: "relative p-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 transition-colors",
      title: `${count} clarification${count !== 1 ? "s" : ""} needed`,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "svg",
          {
            className: "w-5 h-5 text-amber-400",
            fill: "none",
            stroke: "currentColor",
            viewBox: "0 0 24 24",
            xmlns: "http://www.w3.org/2000/svg",
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(
              "path",
              {
                strokeLinecap: "round",
                strokeLinejoin: "round",
                strokeWidth: 2,
                d: "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
              }
            )
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "span",
          {
            className: `absolute -top-1 -right-1 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center ${highPriorityCount > 0 ? "bg-red-500" : "bg-amber-500"}`,
            children: count > 99 ? "99+" : count
          }
        ),
        highPriorityCount > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 animate-ping opacity-75" })
      ]
    }
  );
};
const ClarificationCard = ({
  clarification,
  onClick
}) => {
  const [timeRemaining, setTimeRemaining] = reactExports.useState(
    formatTimeRemaining(clarification.timeout_at)
  );
  reactExports.useEffect(() => {
    if (!clarification.timeout_at) return;
    const interval = setInterval(() => {
      setTimeRemaining(formatTimeRemaining(clarification.timeout_at));
    }, 1e3);
    return () => clearInterval(interval);
  }, [clarification.timeout_at]);
  const severityClass = getSeverityColorClass(clarification.severity);
  const priorityLabel = getPriorityLabel(clarification.priority);
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      onClick,
      className: `p-4 rounded-lg border cursor-pointer transition-all hover:ring-2 hover:ring-white/10 ${severityClass}`,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between items-start gap-2 mb-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-sm font-medium text-white line-clamp-2", children: clarification.description }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "span",
            {
              className: `text-xs px-2 py-0.5 rounded-full shrink-0 ${clarification.priority === 1 ? "bg-red-500/20 text-red-400" : clarification.priority === 2 ? "bg-amber-500/20 text-amber-400" : "bg-blue-500/20 text-blue-400"}`,
              children: priorityLabel
            }
          )
        ] }),
        clarification.detected_term && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-xs text-zinc-500 mb-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium", children: "Term: " }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-zinc-400 font-mono bg-zinc-800 px-1 rounded", children: clarification.detected_term })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-zinc-500 mb-3 line-clamp-2", children: clarification.requirement_text }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between items-center text-xs", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-zinc-400", children: [
            clarification.interpretations.length,
            " option",
            clarification.interpretations.length !== 1 ? "s" : ""
          ] }),
          timeRemaining && timeRemaining !== "expired" && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-amber-400 flex items-center gap-1", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(
              "svg",
              {
                className: "w-3 h-3",
                fill: "none",
                stroke: "currentColor",
                viewBox: "0 0 24 24",
                children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "path",
                  {
                    strokeLinecap: "round",
                    strokeLinejoin: "round",
                    strokeWidth: 2,
                    d: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  }
                )
              }
            ),
            timeRemaining
          ] }),
          timeRemaining === "expired" && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400 text-xs", children: "Auto-resolving..." })
        ] }),
        clarification.interpretations.some((i) => i.is_recommended) && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-2 text-xs text-green-400 flex items-center gap-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("svg", { className: "w-3 h-3", fill: "currentColor", viewBox: "0 0 20 20", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
            "path",
            {
              fillRule: "evenodd",
              d: "M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z",
              clipRule: "evenodd"
            }
          ) }),
          "Has recommended option"
        ] })
      ]
    }
  );
};
const InterpretationOption = ({
  interpretation,
  selected,
  onSelect
}) => {
  const complexityColors = {
    low: "bg-green-500/20 text-green-400",
    medium: "bg-amber-500/20 text-amber-400",
    high: "bg-red-500/20 text-red-400"
  };
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      onClick: onSelect,
      className: `p-4 rounded-lg border cursor-pointer transition-all ${selected ? "border-blue-500 bg-blue-500/10 ring-2 ring-blue-500/50" : "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/50"}`,
      children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between items-start mb-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2 flex-wrap", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium text-white", children: interpretation.label }),
            interpretation.is_recommended && /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full font-medium", children: "Recommended" })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "span",
            {
              className: `text-xs px-2 py-1 rounded-full font-medium ${complexityColors[interpretation.complexity]}`,
              children: interpretation.complexity
            }
          )
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-zinc-400 mb-3", children: interpretation.description }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-xs text-zinc-500 mb-2", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium text-zinc-400", children: "Approach: " }),
          interpretation.technical_approach
        ] }),
        interpretation.trade_offs.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex flex-wrap gap-1.5 mt-3", children: interpretation.trade_offs.map((tradeoff, i) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          "span",
          {
            className: "text-xs bg-zinc-800 text-zinc-400 px-2 py-1 rounded",
            children: tradeoff
          },
          i
        )) }),
        selected && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-1.5 mt-3 text-blue-400 text-sm", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "svg",
            {
              className: "w-4 h-4",
              fill: "currentColor",
              viewBox: "0 0 20 20",
              children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                "path",
                {
                  fillRule: "evenodd",
                  d: "M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z",
                  clipRule: "evenodd"
                }
              )
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { children: "Selected" })
        ] })
      ]
    }
  );
};
const ClarificationEditor = ({
  clarification,
  isOpen,
  isLoading = false,
  onClose,
  onSubmit
}) => {
  const [selectedId, setSelectedId] = reactExports.useState(null);
  const [timeRemaining, setTimeRemaining] = reactExports.useState("");
  reactExports.useEffect(() => {
    if (clarification) {
      const recommended = clarification.interpretations.find((i) => i.is_recommended);
      setSelectedId(recommended?.id || null);
    } else {
      setSelectedId(null);
    }
  }, [clarification]);
  reactExports.useEffect(() => {
    if (!clarification?.timeout_at) return;
    setTimeRemaining(formatTimeRemaining(clarification.timeout_at));
    const interval = setInterval(() => {
      setTimeRemaining(formatTimeRemaining(clarification.timeout_at));
    }, 1e3);
    return () => clearInterval(interval);
  }, [clarification?.timeout_at]);
  if (!isOpen || !clarification) return null;
  const handleSubmit = () => {
    if (selectedId) {
      onSubmit(clarification.id, selectedId);
    }
  };
  const selectedInterpretation = clarification.interpretations.find(
    (i) => i.id === selectedId
  );
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "fixed inset-0 z-50 flex items-center justify-center", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      "div",
      {
        className: "absolute inset-0 bg-black/60 backdrop-blur-sm",
        onClick: onClose
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "relative bg-zinc-900 rounded-xl shadow-2xl border border-zinc-700 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-6 border-b border-zinc-700", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between items-start gap-4", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-xl font-semibold text-white mb-2", children: clarification.description }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3 text-sm", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsxs(
                "span",
                {
                  className: `px-2 py-0.5 rounded-full ${clarification.severity === "high" ? "bg-red-500/20 text-red-400" : clarification.severity === "medium" ? "bg-amber-500/20 text-amber-400" : "bg-blue-500/20 text-blue-400"}`,
                  children: [
                    clarification.severity,
                    " severity"
                  ]
                }
              ),
              timeRemaining && timeRemaining !== "expired" && /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-amber-400 flex items-center gap-1", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "svg",
                  {
                    className: "w-4 h-4",
                    fill: "none",
                    stroke: "currentColor",
                    viewBox: "0 0 24 24",
                    children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "path",
                      {
                        strokeLinecap: "round",
                        strokeLinejoin: "round",
                        strokeWidth: 2,
                        d: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                      }
                    )
                  }
                ),
                timeRemaining,
                " remaining"
              ] })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: onClose,
              className: "text-zinc-400 hover:text-white transition-colors p-1",
              children: /* @__PURE__ */ jsxRuntimeExports.jsx("svg", { className: "w-6 h-6", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                "path",
                {
                  strokeLinecap: "round",
                  strokeLinejoin: "round",
                  strokeWidth: 2,
                  d: "M6 18L18 6M6 6l12 12"
                }
              ) })
            }
          )
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-4 p-3 bg-zinc-800 rounded-lg", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-xs text-zinc-500 block mb-1", children: "From requirement:" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-sm text-zinc-300", children: clarification.requirement_text })
        ] }),
        clarification.detected_term && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "mt-3 text-sm text-zinc-400", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "font-medium", children: "Detected term: " }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("code", { className: "bg-zinc-800 px-2 py-0.5 rounded text-amber-400", children: clarification.detected_term })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 overflow-y-auto p-6", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("h3", { className: "text-sm font-medium text-zinc-300 mb-4", children: "Choose an interpretation:" }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "space-y-4", children: clarification.interpretations.map((interp) => /* @__PURE__ */ jsxRuntimeExports.jsx(
          InterpretationOption,
          {
            interpretation: interp,
            selected: selectedId === interp.id,
            onSelect: () => setSelectedId(interp.id)
          },
          interp.id
        )) })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-6 border-t border-zinc-700 bg-zinc-900/50", children: /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex justify-between items-center", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-sm text-zinc-400", children: selectedInterpretation ? /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { children: [
          "Selected: ",
          /* @__PURE__ */ jsxRuntimeExports.jsx("strong", { className: "text-white", children: selectedInterpretation.label })
        ] }) : /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-amber-400", children: "Please select an option" }) }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex gap-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: onClose,
              className: "px-4 py-2 text-zinc-400 hover:text-white transition-colors",
              disabled: isLoading,
              children: "Cancel"
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsx(
            "button",
            {
              onClick: handleSubmit,
              disabled: !selectedId || isLoading,
              className: `px-6 py-2 rounded-lg font-medium transition-all ${selectedId && !isLoading ? "bg-blue-600 hover:bg-blue-700 text-white" : "bg-zinc-700 text-zinc-500 cursor-not-allowed"}`,
              children: isLoading ? /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center gap-2", children: [
                /* @__PURE__ */ jsxRuntimeExports.jsxs("svg", { className: "animate-spin h-4 w-4", viewBox: "0 0 24 24", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "circle",
                    {
                      className: "opacity-25",
                      cx: "12",
                      cy: "12",
                      r: "10",
                      stroke: "currentColor",
                      strokeWidth: "4",
                      fill: "none"
                    }
                  ),
                  /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "path",
                    {
                      className: "opacity-75",
                      fill: "currentColor",
                      d: "M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    }
                  )
                ] }),
                "Submitting..."
              ] }) : "Confirm Selection"
            }
          )
        ] })
      ] }) })
    ] })
  ] });
};
const ClarificationPanel = ({
  isOpen,
  isLoading = false,
  clarifications,
  statistics,
  onClose,
  onSelect,
  onResolveAll,
  onRefresh
}) => {
  const sortedClarifications = [...clarifications].sort(
    (a, b) => a.priority - b.priority
  );
  const hasRecommended = clarifications.some(
    (c) => c.interpretations.some((i) => i.is_recommended)
  );
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
    isOpen && /* @__PURE__ */ jsxRuntimeExports.jsx(
      "div",
      {
        className: "fixed inset-0 bg-black/30 z-40",
        onClick: onClose
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsxs(
      "div",
      {
        className: `fixed right-0 top-0 h-full w-96 bg-zinc-900 shadow-2xl border-l border-zinc-700 z-50 transform transition-transform duration-300 ease-in-out ${isOpen ? "translate-x-0" : "translate-x-full"}`,
        children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "p-4 border-b border-zinc-700 flex justify-between items-center", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("h2", { className: "text-lg font-semibold text-white", children: "Clarifications Needed" }),
              /* @__PURE__ */ jsxRuntimeExports.jsxs("p", { className: "text-xs text-zinc-400 mt-0.5", children: [
                clarifications.length,
                " pending",
                statistics?.auto_resolved ? ` (${statistics.auto_resolved} auto-resolved)` : ""
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-2", children: [
              onRefresh && /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: onRefresh,
                  disabled: isLoading,
                  className: "p-1.5 text-zinc-400 hover:text-white transition-colors rounded-lg hover:bg-zinc-800",
                  title: "Refresh",
                  children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "svg",
                    {
                      className: `w-5 h-5 ${isLoading ? "animate-spin" : ""}`,
                      fill: "none",
                      stroke: "currentColor",
                      viewBox: "0 0 24 24",
                      children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                        "path",
                        {
                          strokeLinecap: "round",
                          strokeLinejoin: "round",
                          strokeWidth: 2,
                          d: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                        }
                      )
                    }
                  )
                }
              ),
              /* @__PURE__ */ jsxRuntimeExports.jsx(
                "button",
                {
                  onClick: onClose,
                  className: "p-1.5 text-zinc-400 hover:text-white transition-colors rounded-lg hover:bg-zinc-800",
                  children: /* @__PURE__ */ jsxRuntimeExports.jsx("svg", { className: "w-5 h-5", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                    "path",
                    {
                      strokeLinecap: "round",
                      strokeLinejoin: "round",
                      strokeWidth: 2,
                      d: "M6 18L18 6M6 6l12 12"
                    }
                  ) })
                }
              )
            ] })
          ] }),
          statistics && /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "px-4 py-2 bg-zinc-800/50 border-b border-zinc-700 flex gap-4 text-xs", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-zinc-400", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-red-400 font-medium", children: statistics.by_priority.high }),
              " ",
              "high"
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-zinc-400", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-amber-400 font-medium", children: statistics.by_priority.medium }),
              " ",
              "medium"
            ] }),
            /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "text-zinc-400", children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-blue-400 font-medium", children: statistics.by_priority.low }),
              " ",
              "low"
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "p-4 space-y-3 overflow-y-auto h-[calc(100%-12rem)]", children: sortedClarifications.length === 0 ? /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "text-center py-12 text-zinc-500", children: [
            /* @__PURE__ */ jsxRuntimeExports.jsx(
              "svg",
              {
                className: "w-12 h-12 mx-auto mb-3 text-zinc-600",
                fill: "none",
                stroke: "currentColor",
                viewBox: "0 0 24 24",
                children: /* @__PURE__ */ jsxRuntimeExports.jsx(
                  "path",
                  {
                    strokeLinecap: "round",
                    strokeLinejoin: "round",
                    strokeWidth: 2,
                    d: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  }
                )
              }
            ),
            /* @__PURE__ */ jsxRuntimeExports.jsx("p", { children: "All clarifications resolved!" })
          ] }) : sortedClarifications.map((clar) => /* @__PURE__ */ jsxRuntimeExports.jsx(
            ClarificationCard,
            {
              clarification: clar,
              onClick: () => onSelect(clar.id)
            },
            clar.id
          )) }),
          /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "absolute bottom-0 left-0 right-0 p-4 border-t border-zinc-700 bg-zinc-900", children: [
            clarifications.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx(
              "button",
              {
                onClick: onResolveAll,
                disabled: isLoading || !hasRecommended,
                className: `w-full py-3 rounded-lg font-medium transition-all ${hasRecommended && !isLoading ? "bg-blue-600 hover:bg-blue-700 text-white" : "bg-zinc-700 text-zinc-500 cursor-not-allowed"}`,
                title: hasRecommended ? "Resolve all with recommended defaults" : "No recommended options available",
                children: isLoading ? /* @__PURE__ */ jsxRuntimeExports.jsxs("span", { className: "flex items-center justify-center gap-2", children: [
                  /* @__PURE__ */ jsxRuntimeExports.jsxs("svg", { className: "animate-spin h-4 w-4", viewBox: "0 0 24 24", children: [
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "circle",
                      {
                        className: "opacity-25",
                        cx: "12",
                        cy: "12",
                        r: "10",
                        stroke: "currentColor",
                        strokeWidth: "4",
                        fill: "none"
                      }
                    ),
                    /* @__PURE__ */ jsxRuntimeExports.jsx(
                      "path",
                      {
                        className: "opacity-75",
                        fill: "currentColor",
                        d: "M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      }
                    )
                  ] }),
                  "Resolving..."
                ] }) : "Use Defaults for All"
              }
            ),
            clarifications.length > 0 && /* @__PURE__ */ jsxRuntimeExports.jsx("p", { className: "text-xs text-zinc-500 text-center mt-2", children: "Click a card to review and choose an interpretation" })
          ] })
        ]
      }
    )
  ] });
};
function MainLayout() {
  const [activeView, setActiveView] = reactExports.useState("projects");
  const { engineRunning, wsConnected, startEngine, stopEngine } = useEngineStore();
  const { previewProjectId } = useProjectStore();
  const {
    pending: clarifications,
    statistics,
    isPanelOpen,
    isEditorOpen,
    isLoading: clarificationLoading,
    openPanel,
    closePanel,
    selectClarification,
    closeEditor,
    refreshPending,
    submitChoice,
    useAllDefaults
  } = useClarificationStore();
  const selectedClarification = useSelectedClarification();
  const pendingCount = usePendingCount();
  const highPriorityCount = useHighPriorityCount();
  reactExports.useEffect(() => {
    if (!engineRunning) return;
    refreshPending();
    const interval = setInterval(() => {
      refreshPending();
    }, 5e3);
    return () => clearInterval(interval);
  }, [engineRunning, refreshPending]);
  return /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "h-screen flex flex-col bg-engine-darker", children: [
    /* @__PURE__ */ jsxRuntimeExports.jsxs("header", { className: "h-12 bg-engine-dark border-b border-gray-700 flex items-center justify-between px-4", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-6", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-3", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Server, { className: "w-5 h-5 text-engine-primary" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("h1", { className: "text-lg font-semibold", children: "Coding Engine" })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsxs("nav", { className: "flex items-center gap-1", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsxs(
            "button",
            {
              onClick: () => setActiveView("projects"),
              className: `
                flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition
                ${activeView === "projects" ? "bg-engine-primary/20 text-engine-primary" : "text-gray-400 hover:text-white hover:bg-gray-700"}
              `,
              children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(FolderOpen, { className: "w-4 h-4" }),
                "Projects"
              ]
            }
          ),
          /* @__PURE__ */ jsxRuntimeExports.jsxs(
            "button",
            {
              onClick: () => setActiveView("portal"),
              className: `
                flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition
                ${activeView === "portal" ? "bg-engine-primary/20 text-engine-primary" : "text-gray-400 hover:text-white hover:bg-gray-700"}
              `,
              children: [
                /* @__PURE__ */ jsxRuntimeExports.jsx(Store, { className: "w-4 h-4" }),
                "Marketplace"
              ]
            }
          )
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex items-center gap-4", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          ClarificationBadge,
          {
            count: pendingCount,
            highPriorityCount,
            onClick: openPanel
          }
        ),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex items-center gap-2 text-sm", children: wsConnected ? /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(Wifi, { className: "w-4 h-4 text-green-500" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-green-500", children: "Connected" })
        ] }) : /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx(WifiOff, { className: "w-4 h-4 text-gray-500" }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("span", { className: "text-gray-500", children: "Disconnected" })
        ] }) }),
        engineRunning ? /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: stopEngine,
            className: "flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm font-medium transition",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Square, { className: "w-4 h-4" }),
              "Stop Engine"
            ]
          }
        ) : /* @__PURE__ */ jsxRuntimeExports.jsxs(
          "button",
          {
            onClick: startEngine,
            className: "flex items-center gap-2 px-3 py-1.5 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition",
            children: [
              /* @__PURE__ */ jsxRuntimeExports.jsx(Play, { className: "w-4 h-4" }),
              "Start Engine"
            ]
          }
        )
      ] })
    ] }),
    activeView === "projects" ? /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 flex overflow-hidden", children: [
      /* @__PURE__ */ jsxRuntimeExports.jsx("aside", { className: "w-64 bg-engine-dark border-r border-gray-700 flex flex-col", children: /* @__PURE__ */ jsxRuntimeExports.jsx(ProjectList, {}) }),
      /* @__PURE__ */ jsxRuntimeExports.jsxs("main", { className: "flex-1 flex flex-col overflow-hidden", children: [
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "flex-1 overflow-auto", children: /* @__PURE__ */ jsxRuntimeExports.jsx(ProjectSpace, {}) }),
        /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "h-48 border-t border-gray-700", children: /* @__PURE__ */ jsxRuntimeExports.jsx(GenerationMonitor, {}) })
      ] }),
      previewProjectId && /* @__PURE__ */ jsxRuntimeExports.jsx("aside", { className: "w-[500px] bg-engine-dark border-l border-gray-700", children: /* @__PURE__ */ jsxRuntimeExports.jsx(LivePreview, {}) })
    ] }) : /* @__PURE__ */ jsxRuntimeExports.jsx(PortalPage, {}),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      ClarificationPanel,
      {
        isOpen: isPanelOpen,
        isLoading: clarificationLoading,
        clarifications,
        statistics,
        onClose: closePanel,
        onSelect: selectClarification,
        onResolveAll: useAllDefaults,
        onRefresh: refreshPending
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsx(
      ClarificationEditor,
      {
        clarification: selectedClarification,
        isOpen: isEditorOpen,
        isLoading: clarificationLoading,
        onClose: closeEditor,
        onSubmit: submitChoice
      }
    ),
    /* @__PURE__ */ jsxRuntimeExports.jsx(ServiceStatusBar, {})
  ] });
}
const iconMap = {
  error: /* @__PURE__ */ jsxRuntimeExports.jsx(AlertCircle, { className: "w-5 h-5 text-red-400 shrink-0" }),
  success: /* @__PURE__ */ jsxRuntimeExports.jsx(CheckCircle2, { className: "w-5 h-5 text-green-400 shrink-0" }),
  warning: /* @__PURE__ */ jsxRuntimeExports.jsx(AlertTriangle, { className: "w-5 h-5 text-yellow-400 shrink-0" })
};
const borderColorMap = {
  error: "border-l-red-500",
  success: "border-l-green-500",
  warning: "border-l-yellow-500"
};
function ToastContainer() {
  const toasts = useEngineStore((s) => s.toasts);
  const removeToast = useEngineStore((s) => s.removeToast);
  if (toasts.length === 0) return null;
  return /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "fixed bottom-4 right-4 z-[60] flex flex-col gap-2 max-w-sm", children: toasts.map((toast) => /* @__PURE__ */ jsxRuntimeExports.jsxs(
    "div",
    {
      className: `
            animate-slide-in-right
            bg-slate-800 border-l-4 ${borderColorMap[toast.type]}
            rounded-lg shadow-xl p-3 flex items-start gap-3
            text-sm text-slate-200
          `,
      children: [
        iconMap[toast.type],
        /* @__PURE__ */ jsxRuntimeExports.jsxs("div", { className: "flex-1 min-w-0", children: [
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "font-medium text-white truncate", children: toast.title }),
          /* @__PURE__ */ jsxRuntimeExports.jsx("div", { className: "text-slate-400 mt-0.5 line-clamp-2", children: toast.message })
        ] }),
        /* @__PURE__ */ jsxRuntimeExports.jsx(
          "button",
          {
            onClick: () => removeToast(toast.id),
            className: "shrink-0 text-slate-500 hover:text-slate-300 transition-colors",
            children: /* @__PURE__ */ jsxRuntimeExports.jsx(X, { className: "w-4 h-4" })
          }
        )
      ]
    },
    toast.id
  )) });
}
function App() {
  const { checkEngineStatus, connectWebSocket, wsConnected } = useEngineStore();
  const { loadFromOrchestrator } = useProjectStore();
  const wsAttempted = reactExports.useRef(false);
  reactExports.useEffect(() => {
    checkEngineStatus();
    loadFromOrchestrator();
    const interval = setInterval(checkEngineStatus, 3e4);
    return () => clearInterval(interval);
  }, [checkEngineStatus, loadFromOrchestrator]);
  reactExports.useEffect(() => {
    const cleanup = window.electronAPI?.services?.onStatusUpdate?.((status) => {
      if (status?.fastapi?.status === "running" && !wsAttempted.current) {
        console.log("[App] FastAPI is ready — auto-connecting WebSocket");
        wsAttempted.current = true;
        connectWebSocket();
      }
    });
    window.electronAPI?.services?.getStatus?.().then((status) => {
      if (status?.fastapi?.status === "running" && !wsAttempted.current) {
        console.log("[App] FastAPI already running — connecting WebSocket");
        wsAttempted.current = true;
        connectWebSocket();
      }
    }).catch(() => {
    });
    return () => {
      cleanup?.();
    };
  }, [connectWebSocket]);
  return /* @__PURE__ */ jsxRuntimeExports.jsxs(jsxRuntimeExports.Fragment, { children: [
    /* @__PURE__ */ jsxRuntimeExports.jsx(MainLayout, {}),
    /* @__PURE__ */ jsxRuntimeExports.jsx(ToastContainer, {})
  ] });
}
const API_BASE = "";
const CODING_ENGINE_URL = "http://host.docker.internal:8000/api/v1/jobs";
const REQ_ORCHESTRATOR_PROXY = "/orchestrator";
const portAllocations = /* @__PURE__ */ new Map();
let nextVncPort = 6081;
let nextAppPort = 3001;
const webAPI = {
  // ============================================================================
  // Docker Management (via FastAPI backend)
  // ============================================================================
  docker: {
    startEngine: async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/docker/start`, {
          method: "POST"
        });
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` };
        }
        return await response.json();
      } catch (error) {
        return { success: false, error: String(error) };
      }
    },
    stopEngine: async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/docker/stop`, {
          method: "POST"
        });
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` };
        }
        return await response.json();
      } catch (error) {
        return { success: false, error: String(error) };
      }
    },
    getEngineStatus: async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/docker/status`);
        if (!response.ok) {
          return { running: false, services: [] };
        }
        return await response.json();
      } catch {
        return { running: false, services: [] };
      }
    },
    startProject: async (projectId, outputDir) => {
      try {
        let allocation = portAllocations.get(projectId);
        if (!allocation) {
          allocation = { vncPort: nextVncPort++, appPort: nextAppPort++ };
          portAllocations.set(projectId, allocation);
        }
        const response = await fetch(`${API_BASE}/api/v1/dashboard/project/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            projectId,
            outputDir,
            vncPort: allocation.vncPort,
            appPort: allocation.appPort
          })
        });
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` };
        }
        return { success: true, ...allocation };
      } catch (error) {
        return { success: false, error: String(error) };
      }
    },
    stopProject: async (projectId) => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/project/stop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ projectId })
        });
        portAllocations.delete(projectId);
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` };
        }
        return { success: true };
      } catch (error) {
        return { success: false, error: String(error) };
      }
    },
    getProjectStatus: async (projectId) => {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/dashboard/project/status?projectId=${encodeURIComponent(projectId)}`
        );
        if (!response.ok) {
          return { running: false };
        }
        const status = await response.json();
        const allocation = portAllocations.get(projectId);
        return {
          ...status,
          vncPort: allocation?.vncPort,
          appPort: allocation?.appPort
        };
      } catch {
        return { running: false };
      }
    },
    getProjectLogs: async (projectId, tail = 100) => {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/dashboard/project/logs?projectId=${encodeURIComponent(
            projectId
          )}&tail=${tail}`
        );
        if (!response.ok) {
          return `Error: HTTP ${response.status}`;
        }
        const data = await response.json();
        return data.logs || "";
      } catch (error) {
        return `Error fetching logs: ${error}`;
      }
    }
  },
  // ============================================================================
  // Port Allocation
  // ============================================================================
  ports: {
    getVncPort: (projectId) => {
      return portAllocations.get(projectId)?.vncPort;
    },
    getAppPort: (projectId) => {
      return portAllocations.get(projectId)?.appPort;
    },
    getAll: () => {
      return new Map(portAllocations);
    }
  },
  // ============================================================================
  // Engine API
  // ============================================================================
  engine: {
    startGeneration: async (requirementsPath, outputDir) => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ requirementsPath, outputDir })
        });
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` };
        }
        return await response.json();
      } catch (error) {
        return { success: false, error: String(error) };
      }
    },
    getApiUrl: () => API_BASE
  },
  // ============================================================================
  // File System (limited in web mode)
  // ============================================================================
  fs: {
    openFolder: async (path) => {
      alert(`Open folder: ${path}

This requires the desktop app or manual navigation.`);
    },
    showInExplorer: async (path) => {
      alert(`Show in explorer: ${path}

This requires the desktop app or manual navigation.`);
    }
  },
  // ============================================================================
  // req-orchestrator Projects (with tech stacks)
  // ============================================================================
  projects: {
    /**
     * Get all projects from req-orchestrator with tech stack info
     */
    getAll: async () => {
      try {
        const response = await fetch(`${REQ_ORCHESTRATOR_PROXY}/techstack/projects`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        return data.projects || [];
      } catch (error) {
        console.error("Failed to fetch projects from orchestrator:", error);
        return [];
      }
    },
    /**
     * Get requirements for a specific project
     */
    getRequirements: async (projectId) => {
      try {
        const response = await fetch(
          `${REQ_ORCHESTRATOR_PROXY}/techstack/projects/${projectId}/requirements`
        );
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
      } catch (error) {
        console.error("Failed to fetch requirements:", error);
        return [];
      }
    },
    /**
     * Send project(s) from req-orchestrator to Coding Engine for generation
     * This is the main integration point between the two systems
     */
    sendToEngine: async (projectIds, outputDir) => {
      try {
        const response = await fetch(`${REQ_ORCHESTRATOR_PROXY}/techstack/send-to-engine`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_ids: projectIds,
            coding_engine_url: CODING_ENGINE_URL,
            // Connect to Coding Engine
            include_failed: true
            // Include all requirements (validation may not be complete)
          })
        });
        if (!response.ok) {
          const errorText = await response.text();
          return { success: false, error: `HTTP ${response.status}: ${errorText}` };
        }
        return await response.json();
      } catch (error) {
        return { success: false, error: String(error) };
      }
    },
    /**
     * Scan local directories for RE projects (web fallback via FastAPI /local-projects)
     */
    scanLocalDirs: async (_paths) => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/local-projects`);
        if (!response.ok) return [];
        const data = await response.json();
        return (data.projects || []).map((p2) => ({
          project_id: p2.project_id,
          project_name: p2.project_name,
          project_path: p2.project_path,
          source: "local_re",
          tech_stack_tags: [],
          architecture_pattern: "",
          requirements_count: 0,
          user_stories_count: p2.user_story_count || 0,
          tasks_count: 0,
          diagram_count: 0,
          quality_issues: { critical: 0, high: 0, medium: 0 },
          has_api_spec: p2.has_api_docs || false,
          has_master_document: true
        }));
      } catch (error) {
        console.error("[WebAPI] Failed to scan local projects:", error);
        return [];
      }
    },
    /**
     * Get RE project detail (web fallback - returns null, detail requires Electron IPC)
     */
    getREDetail: async (_projectPath) => {
      return null;
    }
  }
};
function initWebAPI() {
  if (typeof window !== "undefined" && !window.electronAPI) {
    window.electronAPI = webAPI;
    console.log("[WebAPI] Initialized web-based API adapter");
  }
}
function initVibeMindAdapter() {
  if (window.vibemind && !window.electronAPI) {
    console.log("[VibeMindAdapter] Initializing adapter for embedded mode");
    window.electronAPI = {
      docker: window.vibemind.docker,
      ports: window.vibemind.ports,
      engine: window.vibemind.engine,
      fs: window.vibemind.fs,
      projects: window.vibemind.projects,
      onPythonMessage: window.vibemind.onPythonMessage,
      sendToPython: window.vibemind.sendToPython,
      closeDashboard: window.vibemind.closeDashboard,
      isEmbedded: window.vibemind.isEmbedded
    };
    console.log("[VibeMindAdapter] Adapter initialized - electronAPI now available");
  } else if (window.electronAPI) {
    console.log("[VibeMindAdapter] Running in standalone mode - electronAPI already available");
  } else {
    console.warn("[VibeMindAdapter] No API available - running in browser dev mode?");
  }
}
if (window.vibemind) {
  initVibeMindAdapter();
  console.log("[Dashboard] Running in VibeMind embedded mode");
} else if (!window.electronAPI) {
  initWebAPI();
  console.log("[Dashboard] Running in web mode");
} else {
  console.log("[Dashboard] Running in Electron standalone mode");
}
client.createRoot(document.getElementById("root")).render(
  /* @__PURE__ */ jsxRuntimeExports.jsx(React$2.StrictMode, { children: /* @__PURE__ */ jsxRuntimeExports.jsx(App, {}) })
);
