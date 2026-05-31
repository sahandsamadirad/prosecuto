/**
 * Prosecuto — 3D avatar stage (Three.js + GLB)
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const DEFAULT_MODEL = '/assets/avatar-khoshtip.glb';
const DEG = Math.PI / 180;

// Perspective offsets to turn the face more to the right (towards the conversation panel)
// while keeping the eyes focused forward/towards the camera for premium eye contact.
const HEAD_YAW_OFFSET_DEG = 12;
const NECK_YAW_OFFSET_DEG = 6;

function pickClip(clips: THREE.AnimationClip[], keywords: string[]) {
  if (!clips?.length) return null;
  const lower = keywords.map((k) => k.toLowerCase());
  return (
    clips.find((c) => lower.some((k) => c.name.toLowerCase().includes(k))) ||
    clips[0]
  );
}

function enhanceMaterials(root: THREE.Object3D, renderer: THREE.WebGLRenderer) {
  const aniso = renderer.capabilities.getMaxAnisotropy();
  root.traverse((child) => {
    if (!(child as THREE.Mesh).isMesh) return;
    const mesh = child as THREE.Mesh;
    mesh.frustumCulled = false;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    mats.forEach((m) => {
      const mat = m as THREE.MeshStandardMaterial;
      if (mat.map) {
        mat.map.anisotropy = aniso;
        mat.map.generateMipmaps = true;
        mat.map.minFilter = THREE.LinearMipmapLinearFilter;
        mat.map.magFilter = THREE.LinearFilter;
      }
      if (mat.normalMap) mat.normalMap.anisotropy = aniso;
      if ('roughness' in mat) mat.roughness = Math.min(mat.roughness ?? 1, 0.72);
      if ('metalness' in mat) mat.metalness = Math.min(mat.metalness ?? 0, 0.15);
      mat.needsUpdate = true;
    });
  });
}

export class AvatarStage {
  container: HTMLElement;
  modelUrl: string;
  speaking = false;
  disposed = false;
  pivot: THREE.Group | null = null;
  rig: THREE.Object3D | null = null;
  headBone: THREE.Bone | null = null;
  neckBone: THREE.Bone | null = null;
  leftEye: THREE.Bone | null = null;
  rightEye: THREE.Bone | null = null;
  lookTarget = new THREE.Vector3();
  private _tmp = new THREE.Vector3();
  private _quat = new THREE.Quaternion();
  private _offsetQuat = new THREE.Quaternion();
  private _eyeQuat = new THREE.Quaternion();
  private _euler = new THREE.Euler(0, 0, 0, 'YXZ');
  private _pointer = { x: 0, y: 0 };
  private _pointerSmooth = { x: 0, y: 0 };
  private _leftEyeBaseRot: THREE.Quaternion | null = null;
  private _rightEyeBaseRot: THREE.Quaternion | null = null;
  private _headBaseRot: THREE.Quaternion | null = null;
  private _neckBaseRot: THREE.Quaternion | null = null;
  scene: THREE.Scene;
  clock: THREE.Clock;
  mixer: THREE.AnimationMixer | null = null;
  idleAction: THREE.AnimationAction | null = null;
  speakAction: THREE.AnimationAction | null = null;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  private _onResize: () => void;
  private _ro: ResizeObserver;
  private _onPointerMove: (e: PointerEvent) => void;
  private _onPointerLeave: () => void;
  private _tick: () => void;
  private _raf = 0;

  constructor(container: HTMLElement, options: { modelUrl?: string } = {}) {
    this.container = container;
    this.modelUrl = options.modelUrl || DEFAULT_MODEL;

    this.scene = new THREE.Scene();
    this.clock = new THREE.Clock();

    const { width, height } = this._size();
    this.camera = new THREE.PerspectiveCamera(24, width / height, 0.02, 40);

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    this.renderer.setSize(width, height);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.domElement.className = 'avatar-3d-canvas';
    container.appendChild(this.renderer.domElement);

    const key = new THREE.DirectionalLight(0xffffff, 1.55);
    key.position.set(0.6, 1.4, 2.2);
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0xd4e8f7, 0.75);
    fill.position.set(-1.8, 0.8, 1.4);
    this.scene.add(fill);

    const rim = new THREE.DirectionalLight(0xfff3d6, 0.45);
    rim.position.set(0.2, 1.1, -1.6);
    this.scene.add(rim);

    this.scene.add(new THREE.AmbientLight(0xf0f8ff, 0.42));
    this.scene.add(new THREE.HemisphereLight(0xeaf4fc, 0x5c6f85, 0.35));

    this._onResize = () => this._resize();
    this._ro = new ResizeObserver(this._onResize);
    this._ro.observe(container);

    this._onPointerMove = (e: PointerEvent) => {
      const x = (e.clientX / window.innerWidth) * 2 - 1;
      const y = (e.clientY / window.innerHeight) * 2 - 1;
      this._pointer.x = Math.max(-1, Math.min(1, x));
      this._pointer.y = Math.max(-1, Math.min(1, y));
    };
    this._onPointerLeave = () => {
      this._pointer.x = 0;
      this._pointer.y = 0;
    };
    window.addEventListener('pointermove', this._onPointerMove, { passive: true });
    window.addEventListener('pointerleave', this._onPointerLeave);
    document.addEventListener('mouseleave', this._onPointerLeave);

    this._load();
    this._tick = this._tickLoop.bind(this);
    this._raf = requestAnimationFrame(this._tick);
  }

  _size() {
    const w = this.container.clientWidth || 400;
    const h = this.container.clientHeight || 500;
    return { width: w, height: h };
  }

  _resize() {
    const { width, height } = this._size();
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    if (this.rig) this._framePortrait();
  }

  _findBones(root: THREE.Object3D) {
    root.traverse((child) => {
      if (!(child as THREE.Bone).isBone) return;
      const bone = child as THREE.Bone;
      if (bone.name === 'Head') this.headBone = bone;
      if (bone.name === 'Neck') this.neckBone = bone;
      if (bone.name === 'LeftEye') this.leftEye = bone;
      if (bone.name === 'RightEye') this.rightEye = bone;
    });

    if (this.headBone) this._headBaseRot = this.headBone.quaternion.clone();
    if (this.neckBone) this._neckBaseRot = this.neckBone.quaternion.clone();
    if (this.leftEye) this._leftEyeBaseRot = this.leftEye.quaternion.clone();
    if (this.rightEye) this._rightEyeBaseRot = this.rightEye.quaternion.clone();
  }

  _applyCursorTracking(dt: number) {
    if (!this.headBone) return;

    const ease = 1 - Math.pow(0.001, dt);
    this._pointerSmooth.x += (this._pointer.x - this._pointerSmooth.x) * ease;
    this._pointerSmooth.y += (this._pointer.y - this._pointerSmooth.y) * ease;

    const px = this._pointerSmooth.x;
    const py = this._pointerSmooth.y;

    // Keep neck turn perfectly static in its 3/4 listening posture
    if (this.neckBone) {
      this._euler.set(0, NECK_YAW_OFFSET_DEG * DEG, 0, 'YXZ');
      this._offsetQuat.setFromEuler(this._euler);
      this.neckBone.quaternion.multiply(this._offsetQuat);
    }

    // Keep head/face perspective perfectly static in its aligned listening posture (no mouse movement)
    const headYawDeg = HEAD_YAW_OFFSET_DEG;
    const headPitchDeg = 0;
    this._euler.set(headPitchDeg * DEG, headYawDeg * DEG, 0, 'YXZ');
    this._offsetQuat.setFromEuler(this._euler);
    this.headBone.quaternion.multiply(this._offsetQuat);

    if (this.leftEye && this.rightEye && this._leftEyeBaseRot && this._rightEyeBaseRot) {
      // Natural, symmetric eye tracking centered in the middle of the sockets (no corner offsets)
      // Maximum yaw is 6 degrees, pitch is 4.5 degrees, keeping pupils perfectly centered.
      const eyeYawDeg = px * 6;
      const eyePitchDeg = py * 4.5;
      this._euler.set(eyePitchDeg * DEG, eyeYawDeg * DEG, 0, 'YXZ');
      this._eyeQuat.setFromEuler(this._euler);

      this.leftEye.quaternion.copy(this._leftEyeBaseRot).multiply(this._eyeQuat);
      this.rightEye.quaternion.copy(this._rightEyeBaseRot).multiply(this._eyeQuat);
    }
  }

  _faceTowardCameraScore() {
    const toCamera = new THREE.Vector3(0, 0, 1);

    if (this.leftEye && this.rightEye && this.headBone) {
      const le = new THREE.Vector3();
      const re = new THREE.Vector3();
      const head = new THREE.Vector3();
      this.leftEye.getWorldPosition(le);
      this.rightEye.getWorldPosition(re);
      this.headBone.getWorldPosition(head);
      const eyeMid = le.add(re).multiplyScalar(0.5);
      const faceForward = eyeMid.sub(head).normalize();
      return faceForward.dot(toCamera);
    }

    if (this.headBone) {
      const forward = new THREE.Vector3(0, 0, -1);
      forward.applyQuaternion(this.headBone.getWorldQuaternion(this._quat));
      return forward.dot(toCamera);
    }

    return 0;
  }

  _orientTowardCamera() {
    if (!this.pivot || !this.rig) return;
    // Rotate the avatar's body slightly to the right (about 12.6 degrees) 
    // to face the conversation panel, creating a premium 3/4 portrait view.
    this.pivot.rotation.y = 0.22;
    this.pivot.updateMatrixWorld(true);
  }

  _framePortrait() {
    if (!this.rig) return;

    if (this.pivot) {
      this.pivot.updateMatrixWorld(true);
    } else {
      this.rig.updateMatrixWorld(true);
    }

    const full = new THREE.Box3().setFromObject(this.rig);
    const bodyH = full.max.y - full.min.y;

    let neckY = full.min.y + bodyH * 0.78;
    let headY = full.min.y + bodyH * 0.92;
    let topY = full.max.y;

    if (this.headBone && this.neckBone) {
      this.neckBone.getWorldPosition(this._tmp);
      neckY = this._tmp.y;
      this.headBone.getWorldPosition(this._tmp);
      headY = this._tmp.y;
      topY = Math.max(topY, headY + bodyH * 0.06);
    }

    const portraitBottom = neckY - bodyH * 0.03;
    const portraitTop = topY + bodyH * 0.015;
    const portraitMid = (portraitBottom + portraitTop) * 0.5;
    const portraitH = portraitTop - portraitBottom;

    this.lookTarget.set(0, headY - bodyH * 0.02, 0);

    const vFov = this.camera.fov * DEG;
    const fill = 0.94;
    const dist = (portraitH * 0.5) / (Math.tan(vFov * 0.5) * fill);

    this.camera.position.set(0, portraitMid + portraitH * 0.04, dist);
    this.camera.lookAt(this.lookTarget);
    this.camera.updateProjectionMatrix();
  }

  _setupPortrait(object: THREE.Object3D) {
    enhanceMaterials(object, this.renderer);
    this._findBones(object);

    this.pivot = new THREE.Group();
    this.rig = object;
    this.pivot.add(object);
    this.scene.add(this.pivot);

    const box = new THREE.Box3().setFromObject(object);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    object.position.x -= center.x;
    object.position.z -= center.z;
    object.position.y -= box.min.y;

    const targetBodyH = 1.72;
    const scale = targetBodyH / size.y;
    object.scale.setScalar(scale);

    this._orientTowardCamera();
    this._framePortrait();
  }

  _load() {
    const loader = new GLTFLoader();
    loader.load(
      this.modelUrl,
      (gltf) => {
        if (this.disposed) return;
        this._setupPortrait(gltf.scene);
        this.container.classList.add('avatar-3d-ready');

        if (gltf.animations?.length) {
          this.mixer = new THREE.AnimationMixer(this.rig!);
          const idleClip = pickClip(gltf.animations, ['idle', 'stand', 'breath', 'rest', 'head']);
          const speakClip = pickClip(gltf.animations, ['talk', 'speak', 'speech', 'mouth']);
          const useSpeak = speakClip && speakClip !== idleClip ? speakClip : idleClip;

          if (idleClip) {
            this.idleAction = this.mixer.clipAction(idleClip);
            this.idleAction.setLoop(THREE.LoopRepeat, Infinity);
          }
          if (useSpeak) {
            this.speakAction = this.mixer.clipAction(useSpeak);
            this.speakAction.setLoop(THREE.LoopRepeat, Infinity);
          }
          this.idleAction?.play();
          this._framePortrait();
        }
      },
      undefined,
      (err) => {
        console.error('[ProsecutoAvatar] Failed to load model:', err);
        this.container.classList.add('avatar-3d-error');
      }
    );
  }

  setSpeaking(active: boolean) {
    this.speaking = !!active;
    if (!this.mixer) return;

    if (this.speakAction && this.idleAction && this.speakAction !== this.idleAction) {
      const fade = 0.35;
      if (this.speaking) {
        this.idleAction.fadeOut(fade);
        this.speakAction.reset().fadeIn(fade).play();
      } else {
        this.speakAction.fadeOut(fade);
        this.idleAction.reset().fadeIn(fade).play();
      }
      return;
    }

    const action = this.speakAction || this.idleAction;
    if (action) action.timeScale = this.speaking ? 1.35 : 1;
  }

  _tickLoop() {
    if (this.disposed) return;
    const dt = Math.min(this.clock.getDelta(), 0.1);

    // Reset tracking bones to their base/rest poses before updating the mixer,
    // to prevent rotation offsets from accumulating frame-over-frame.
    if (this.headBone && this._headBaseRot) {
      this.headBone.quaternion.copy(this._headBaseRot);
    }
    if (this.neckBone && this._neckBaseRot) {
      this.neckBone.quaternion.copy(this._neckBaseRot);
    }

    // Update the animation mixer (idle breathing, talking mouth, etc.)
    this.mixer?.update(dt);

    // Apply cursor tracking offset on top of the animated pose
    this._applyCursorTracking(dt);

    if (this.headBone) {
      this.headBone.getWorldPosition(this._tmp);
      this.lookTarget.copy(this._tmp);
      this.lookTarget.y -= 0.012;
      this.camera.lookAt(this.lookTarget);
    }

    this.renderer.render(this.scene, this.camera);
    this._raf = requestAnimationFrame(this._tick);
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this._raf);
    this._ro?.disconnect();
    window.removeEventListener('pointermove', this._onPointerMove);
    window.removeEventListener('pointerleave', this._onPointerLeave);
    document.removeEventListener('mouseleave', this._onPointerLeave);
    this.mixer?.stopAllAction();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      if (mesh.material) {
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        mats.forEach((m) => (m as THREE.Material).dispose?.());
      }
    });
  }
}

export function mount(container: HTMLElement, options?: { modelUrl?: string }) {
  if (!container) return null;
  return new AvatarStage(container, options);
}
