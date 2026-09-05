// Original file: model.proto

import type { RailType as _tasklattice_guard_control_v1_RailType, RailType__Output as _tasklattice_guard_control_v1_RailType__Output } from '../../../../tasklattice/guard/control/v1/RailType.js';

/**
 * Bind one stable product capability on one Rail surface to a registered
 * Model implementation. Policies reference contract_refs, never model IDs.
 */
export interface CapabilityBinding {
  'bindingId'?: (string);
  'capabilityRef'?: (string);
  'railType'?: (_tasklattice_guard_control_v1_RailType);
  'implementationRef'?: (string);
  'modelRef'?: (string);
  'profileRef'?: (string);
  'contractRefs'?: (string)[];
}

/**
 * Bind one stable product capability on one Rail surface to a registered
 * Model implementation. Policies reference contract_refs, never model IDs.
 */
export interface CapabilityBinding__Output {
  'bindingId': (string);
  'capabilityRef': (string);
  'railType': (_tasklattice_guard_control_v1_RailType__Output);
  'implementationRef': (string);
  'modelRef': (string);
  'profileRef': (string);
  'contractRefs': (string)[];
}
