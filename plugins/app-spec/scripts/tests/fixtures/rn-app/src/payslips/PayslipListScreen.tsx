import axios from 'axios';
import React from 'react';
import { Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';

const BASE = 'https://api.sample.test/employee/api/v1';

export const loadPayslips = (id: string) => axios.get(`${BASE}/employees/${id}/payslips`);

export const PayslipListScreen = () => {
  const { t } = useTranslation();
  return (
    <View>
      <Text testID="pay.list.title">{t('payslip.title')}</Text>
    </View>
  );
};
