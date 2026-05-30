'use client';

import { useEffect, useRef } from 'react';
import { AvatarStage, mount } from '@/lib/avatar-stage';

type AvatarMountProps = {
  speaking?: boolean;
  modelUrl?: string;
};

export default function AvatarMount({ speaking = false, modelUrl }: AvatarMountProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<AvatarStage | null>(null);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return undefined;
    stageRef.current = mount(el, { modelUrl }) ?? null;
    return () => {
      stageRef.current?.dispose();
      stageRef.current = null;
    };
  }, [modelUrl]);

  useEffect(() => {
    stageRef.current?.setSpeaking(speaking);
  }, [speaking]);

  return <div className="avatar-3d-mount" ref={mountRef} aria-hidden />;
}
