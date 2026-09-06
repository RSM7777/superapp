// Every tappable surface in the app is a react-native <Pressable>, and RN's
// Pressable renders NO feedback of its own — that is why cards, tiles and
// rows felt dead under the finger. This is a drop-in replacement: same API,
// same layout (it renders the very same element, no extra wrapper view, so
// flex and absolute positioning behave exactly as before), plus a press
// state you can actually feel.
//
// Import it instead of react-native's Pressable and every call site in the
// file gets feedback for free.
import React from "react";
import { Pressable as RNPressable } from "react-native";
import type { PressableProps, StyleProp, ViewStyle } from "react-native";

type StyleArg = { pressed: boolean };
type PressStyle =
  | StyleProp<ViewStyle>
  | ((state: StyleArg) => StyleProp<ViewStyle>);

// Dim and shrink, in proportion to how big the target is: a full-width card
// wants a subtler nudge than a small pill, or it reads as a glitch.
const FEEDBACK = {
  card: { opacity: 0.82, transform: [{ scale: 0.985 }] },
  control: { opacity: 0.68, transform: [{ scale: 0.96 }] },
} as const;

export type TapProps = Omit<PressableProps, "style"> & {
  style?: PressStyle;
  /** "card" (default) for cards, tiles and rows; "control" for pills,
   *  buttons, chips and icons, which take a firmer press. */
  feel?: keyof typeof FEEDBACK;
};

export function Pressable({ style, feel = "card", disabled, ...rest }: TapProps) {
  const resolve = React.useCallback(
    (state: StyleArg) => {
      const base = typeof style === "function" ? style(state) : style;
      // Disabled things must not pretend to respond.
      if (!state.pressed || disabled) return base;
      return [base, FEEDBACK[feel]] as StyleProp<ViewStyle>;
    },
    [style, feel, disabled],
  );
  return <RNPressable style={resolve} disabled={disabled} {...rest} />;
}

export default Pressable;
