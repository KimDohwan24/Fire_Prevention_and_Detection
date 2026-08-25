import React from 'react';
import { Outlet } from 'react-router-dom';
import GlobalFireAlertOverlay from '../GlobalFireAlertOverlay';
import FireAlertProvider from '../../context/FireAlertContext';

export default function ProtectedAppLayout() {
  return (
    <FireAlertProvider>
      <Outlet />
      <GlobalFireAlertOverlay />
    </FireAlertProvider>
  );
}
