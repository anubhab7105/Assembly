import {
  ThreeUIIntro,
  ParticleWordmark,
  AudioWordmark,
  GalleryHeading,
  type NeuformIsolatedEffectProps,
} from "./NeuformIsolatedEffects";

export type TextAnimationVariant =
  | "threeui-intro"
  | "particle-wordmark"
  | "audio-wordmark"
  | "gallery-heading";

export type TextAnimationCollectionProps = NeuformIsolatedEffectProps & {
  variant?: TextAnimationVariant;
  text?: string;
  logoSvg?: string;
};

export function TextAnimationCollection({
  variant = "threeui-intro",
  ...props
}: TextAnimationCollectionProps) {
  switch (variant) {
    case "threeui-intro":
      return <ThreeUIIntro {...props} />;
    case "particle-wordmark":
      return <ParticleWordmark {...props} />;
    case "audio-wordmark":
      return <AudioWordmark {...props} />;
    case "gallery-heading":
      return <GalleryHeading {...props} />;
    default:
      return <ThreeUIIntro {...props} />;
  }
}

