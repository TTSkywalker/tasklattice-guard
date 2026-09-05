// Original file: model.proto

import type { CapabilityValidationCase as _tasklattice_guard_control_v1_CapabilityValidationCase, CapabilityValidationCase__Output as _tasklattice_guard_control_v1_CapabilityValidationCase__Output } from '../../../../tasklattice/guard/control/v1/CapabilityValidationCase.js';

/**
 * Behavioural evidence from the same NeMo compiler and runtime used for traffic.
 */
export interface CapabilityValidationResult {
  'requestId'?: (string);
  'passed'?: (boolean);
  'message'?: (string);
  /**
   * Total compilation and evaluation duration in milliseconds.
   */
  'latencyMs'?: (number);
  /**
   * Compiler-selected NeMo execution profile; never a client-selected bypass.
   */
  'runtimeProfile'?: (string);
  'cases'?: (_tasklattice_guard_control_v1_CapabilityValidationCase)[];
}

/**
 * Behavioural evidence from the same NeMo compiler and runtime used for traffic.
 */
export interface CapabilityValidationResult__Output {
  'requestId': (string);
  'passed': (boolean);
  'message': (string);
  /**
   * Total compilation and evaluation duration in milliseconds.
   */
  'latencyMs': (number);
  /**
   * Compiler-selected NeMo execution profile; never a client-selected bypass.
   */
  'runtimeProfile': (string);
  'cases': (_tasklattice_guard_control_v1_CapabilityValidationCase__Output)[];
}
