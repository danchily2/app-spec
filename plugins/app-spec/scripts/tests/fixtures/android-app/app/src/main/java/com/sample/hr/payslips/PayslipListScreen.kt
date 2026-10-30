package com.sample.hr.payslips

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.sample.hr.R

@Composable
fun PayslipListScreen() {
    Text(
        text = stringResource(R.string.payslip_title),
        modifier = Modifier.testTag("pay.list.title"),
    )
}
