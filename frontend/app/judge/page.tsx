import type { Metadata } from 'next';
import JudgeApp from '@/components/judge/JudgeApp';

export const metadata: Metadata = {
  title: 'Judge Mode — Mock Trial',
};

export default function JudgePage() {
  return <JudgeApp />;
}
