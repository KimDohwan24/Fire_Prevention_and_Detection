import React, { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Video, Flame, ShieldAlert, MapPin, Layers } from 'lucide-react';

const KOREA_MAP_CENTER = [36.35, 127.85];
const KOREA_MAP_BOUNDS = [[33.0, 124.5], [38.6, 130.0]];
const KOREA_MAP_MIN_ZOOM = 7;

// Leaflet 기본 아이콘 경로 지정 (Asset 404 예방)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// 지도 중심 자동 재설정 컨트롤 컴포넌트
// - 사용자가 명시적으로 다른 CCTV를 선택했을 때만 지도를 이동
// - 폴링 리렌더 시에는 사용자가 설정한 zoom/pan을 유지
function MapRecenter({ center, zoom, selectedId }) {
  const map = useMap();
  const prevSelectedId = useRef(selectedId);
  const isInitialized = useRef(false);

  useEffect(() => {
    // 초기 선택 CCTV 때문에 국가 전체 보기 화면이 바로 확대되지 않도록 한다.
    if (!isInitialized.current) {
      prevSelectedId.current = selectedId;
      isInitialized.current = true;
      return;
    }

    // selectedId가 실제로 변경되었을 때만 지도 이동 (폴링 리렌더 무시)
    if (selectedId !== prevSelectedId.current) {
      prevSelectedId.current = selectedId;
      const lat = Number(center?.[0]);
      const lng = Number(center?.[1]);
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        map.setView([lat, lng], zoom || map.getZoom());
      }
    }
  }, [center, zoom, selectedId, map]);
  return null;
}

// 지도 타일 공급자 정의 (1번 CartoDB 추천 & OSM/VWorld 호환)
const TILE_PROVIDERS = {
  cartoLight: {
    name: 'CartoDB Positron (라이트)',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  },
  cartoDark: {
    name: 'CartoDB Dark Matter (다크)',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  },
  osm: {
    name: 'OpenStreetMap (기본)',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
};

// 커스텀 DIV 아이콘 생성 함수
const createCustomIcon = (type, alertLevel = null) => {
  if (type === 'firestation') {
    return L.divIcon({
      className: 'custom-leaflet-marker',
      html: `
        <div style="
          background-color: #ef4444;
          color: white;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
          border: 2px solid white;
        ">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });
  }

  if (alertLevel === 'detecting') {
    return L.divIcon({
      className: 'custom-leaflet-marker detecting-pulse',
      html: `
        <div style="position: relative; width: 36px; height: 36px;">
          <div style="
            position: absolute;
            inset: 0;
            border-radius: 50%;
            background-color: #f59e0b;
            opacity: 0.7;
            animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
          "></div>
          <div style="
            position: relative;
            background-color: #f59e0b;
            color: white;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 10px rgba(245, 158, 11, 0.5);
            border: 2px solid white;
          ">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 3.5z"/>
            </svg>
          </div>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
  }

  if (alertLevel === 'confirmed' || alertLevel === 'fire' || alertLevel === true) {
    return L.divIcon({
      className: 'custom-leaflet-marker emergency-pulse',
      html: `
        <div style="position: relative; width: 36px; height: 36px;">
          <div style="
            position: absolute;
            inset: 0;
            border-radius: 50%;
            background-color: #ef4444;
            opacity: 0.75;
            animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
          "></div>
          <div style="
            position: relative;
            background-color: #dc2626;
            color: white;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 10px rgba(239, 68, 68, 0.5);
            border: 2px solid white;
          ">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 3.5z"/>
            </svg>
          </div>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
  }

  // 일반 CCTV 마커
  return L.divIcon({
    className: 'custom-leaflet-marker',
    html: `
      <div style="
        background-color: #171717;
        color: white;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
        border: 2px solid white;
      ">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="23 7 16 12 23 17 23 7"/>
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
};

export default function GisMap({
  cctvList = [],
  agencyList = [],
  selectedCCTV,
  onSelectCCTV,
  showFireStation = true,
  center = KOREA_MAP_CENTER,
  zoom = 7
}) {
  const [tileKey, setTileKey] = useState('osm');
  const activeTile = TILE_PROVIDERS[tileKey] || TILE_PROVIDERS.cartoLight;
  const mapRef = useRef(null);

  // 선택된 CCTV가 있으면 지도 센터 자동 재설정
  const mapCenter = selectedCCTV && selectedCCTV.lat && selectedCCTV.lng
    ? [parseFloat(selectedCCTV.lat), parseFloat(selectedCCTV.lng)]
    : center;

  // 팝업 내부 "실시간 CCTV 관제" 버튼 클릭 핸들러
  const handlePopupSelect = (cctv) => {
    if (onSelectCCTV) onSelectCCTV(cctv);
    // Leaflet 팝업을 닫아야 우측 패널이 정상 전환됨
    if (mapRef.current) {
      mapRef.current.closePopup();
    }
  };

  return (
    <div className="relative w-full h-full rounded-2xl overflow-hidden shadow-inner border border-neutral-200">
      {/* 타일 선택 툴바 컨트롤 */}
      <div className="absolute top-3 right-3 z-[1000] bg-white/90 backdrop-blur-md px-3 py-1.5 rounded-xl shadow-md border border-neutral-200 flex items-center space-x-2 text-xs font-medium text-neutral-700">
        <Layers className="w-4 h-4 text-neutral-500" />
        <span>GIS 배경:</span>
        <select
          value={tileKey}
          onChange={(e) => setTileKey(e.target.value)}
          className="bg-transparent font-medium text-neutral-900 focus:outline-none cursor-pointer"
        >
          {Object.entries(TILE_PROVIDERS).map(([key, provider]) => (
            <option key={key} value={key}>
              {provider.name}
            </option>
          ))}
        </select>
      </div>

      <MapContainer
        center={center}
        zoom={zoom}
        minZoom={KOREA_MAP_MIN_ZOOM}
        maxBounds={KOREA_MAP_BOUNDS}
        maxBoundsViscosity={1}
        worldCopyJump={false}
        style={{ width: '100%', height: '100%', minHeight: '380px' }}
        zoomControl={false}
        ref={mapRef}
      >
        <MapRecenter center={mapCenter} zoom={selectedCCTV ? 15 : zoom} selectedId={selectedCCTV?.cctv_no || null} />
        
        {/* 선택한 GIS 배경 타일 */}
        <TileLayer
          url={activeTile.url}
          attribution={activeTile.attribution}
          maxZoom={19}
        />

        {/* 북한·일본 등 주변 지역은 배경 타일을 가려 한국 영역만 표시 */}
        {/* 관할 소방서 마커 */}
        {showFireStation && agencyList.map((agency) => {
          const lat = parseFloat(agency.lat || agency.agency_lat);
          const lng = parseFloat(agency.lng || agency.agency_lng);
          if (!lat || !lng) return null;

          return (
            <Marker
              key={`agency-${agency.agency_no || agency.name}`}
              position={[lat, lng]}
              icon={createCustomIcon('firestation')}
            >
              <Popup className="leaflet-custom-popup">
                <div className="p-1 space-y-1">
                  <div className="flex items-center space-x-1.5 text-red-600 font-bold text-sm">
                    <ShieldAlert className="w-4 h-4" />
                    <span>{agency.agency_name || agency.name}</span>
                  </div>
                  <p className="text-xs text-neutral-600">{agency.address || '관할 구역 긴급 응급 센터'}</p>
                  <p className="text-xs font-semibold text-neutral-800">{agency.phone || '119 상황실'}</p>
                </div>
              </Popup>
            </Marker>
          );
        })}

        {/* CCTV 자산 마커 목록 */}
        {cctvList.map((cctv) => {
          const lat = parseFloat(cctv.lat);
          const lng = parseFloat(cctv.lng);
          if (!lat || !lng) return null;

          const isEmergency = cctv.status === 'FIRE' || cctv.status === 'EMERGENCY' || cctv.isEmergency;
          const alertLevel = cctv.alertLevel || (isEmergency ? 'confirmed' : null);
          const hasAlert = alertLevel === 'detecting' || alertLevel === 'confirmed';
          const isSelected = selectedCCTV && selectedCCTV.cctv_no === cctv.cctv_no;

          return (
            <React.Fragment key={`cctv-${cctv.cctv_no || cctv.name}`}>
              {/* 긴급 화재 발생 시 주변 감지 범위 원 표시 */}
              {hasAlert && (
                <Circle
                  center={[lat, lng]}
                  radius={350}
                  pathOptions={{
                    color: alertLevel === 'detecting' ? '#f59e0b' : '#ef4444',
                    fillColor: alertLevel === 'detecting' ? '#f59e0b' : '#ef4444',
                    fillOpacity: 0.25,
                    weight: 2
                  }}
                />
              )}

              <Marker
                position={[lat, lng]}
                icon={createCustomIcon('cctv', alertLevel)}
                eventHandlers={{
                  click: () => {
                    if (onSelectCCTV) onSelectCCTV(cctv);
                  }
                }}
              >
                <Popup>
                  <div className="p-1 space-y-1.5 text-xs">
                    <div className="flex items-center space-x-1 font-bold text-neutral-900 text-sm">
                      <Video className="w-4 h-4 text-neutral-700" />
                      <span>{cctv.cctv_name || cctv.name}</span>
                    </div>
                    <div className="flex items-center space-x-1 text-neutral-500">
                      <MapPin className="w-3.5 h-3.5" />
                      <span>{cctv.address || '설치 위치 정보'}</span>
                    </div>
                    {hasAlert && (
                      <div className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full font-bold text-[11px] ${alertLevel === 'detecting' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                        <Flame className="w-3 h-3 fill-current" />
                        <span>화재 감지 긴급 상황!</span>
                      </div>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePopupSelect(cctv);
                      }}
                      className="w-full mt-2 py-1.5 bg-black text-white rounded-lg text-xs font-bold hover:bg-neutral-800 transition cursor-pointer"
                    >
                      실시간 CCTV 관제
                    </button>
                  </div>
                </Popup>
              </Marker>
            </React.Fragment>
          );
        })}
      </MapContainer>
    </div>
  );
}
