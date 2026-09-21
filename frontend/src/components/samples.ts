/** 自己画的示例图（版权干净），选的都是拼豆最常见的题材。 */
export const SAMPLES = [
  { file: "strawberry.png", label: "草莓" },
  { file: "cat.png", label: "小猫" },
  { file: "mushroom.png", label: "蘑菇" },
] as const;

export type Sample = (typeof SAMPLES)[number];
