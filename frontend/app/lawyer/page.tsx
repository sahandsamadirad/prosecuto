import type { Metadata } from 'next';
import LawyerApp from '@/components/lawyer/LawyerApp';

export const metadata: Metadata = {
  title: 'Lawyer Mode — Alex',
};

export default function LawyerPage() {
  return <LawyerApp />;
}
