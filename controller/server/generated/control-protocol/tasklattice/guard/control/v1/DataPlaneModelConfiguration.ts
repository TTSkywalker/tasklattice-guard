// Original file: model.proto

import type { ModelRuntime as _tasklattice_guard_control_v1_ModelRuntime, ModelRuntime__Output as _tasklattice_guard_control_v1_ModelRuntime__Output } from '../../../../tasklattice/guard/control/v1/ModelRuntime.js';
import type { CapabilityBinding as _tasklattice_guard_control_v1_CapabilityBinding, CapabilityBinding__Output as _tasklattice_guard_control_v1_CapabilityBinding__Output } from '../../../../tasklattice/guard/control/v1/CapabilityBinding.js';

/**
 * Complete data-plane projection of one validated Model configuration
 * revision. Only model-backed capability bindings needed by Runner are included.
 */
export interface DataPlaneModelConfiguration {
  'revisionId'?: (string);
  'revision'?: (number);
  'runtimes'?: (_tasklattice_guard_control_v1_ModelRuntime)[];
  'bindings'?: (_tasklattice_guard_control_v1_CapabilityBinding)[];
}

/**
 * Complete data-plane projection of one validated Model configuration
 * revision. Only model-backed capability bindings needed by Runner are included.
 */
export interface DataPlaneModelConfiguration__Output {
  'revisionId': (string);
  'revision': (number);
  'runtimes': (_tasklattice_guard_control_v1_ModelRuntime__Output)[];
  'bindings': (_tasklattice_guard_control_v1_CapabilityBinding__Output)[];
}
